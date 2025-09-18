from app.user_session.schemas import UserSessionCreate
from app.user_session.models.user_session import UserSession
from app.submission.models.submisson import Submission
from app.problem_ref.models.problem_ref import ProblemReference
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db

import redis
from datetime import datetime
import asyncio
import time
from typing import cast
import logging
import os

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    force=True   # <- 기존 설정 무시하고 강제 재설정
)
logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST_user_group", "aprofi_redis_ver_user_group")
REDIS_PORT = int(os.getenv("REDIS_PORT_user_group", "6379"))
REDIS_DB   = int(os.getenv("REDIS_DB_user_group", "0"))

r = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    decode_responses=True,
    socket_timeout=2,
)
# 추가 필요 함수 모음----------------------------------

async def get_problem_reference_id(db: AsyncSession, group_id: int, workbook_id: int, problem_id: int) -> int | None:
    """
    page의 (group_id, workbook_id, problem_id) 조합으로 ProblemReference(또는 유사 엔티티)의 PK 조회.
    실제 테이블/컬럼명에 맞게 수정해.
    """
    # 예시: ProblemReference(group_id, workbook_id, problem_id, problem_reference_id)
    q = (
        select(ProblemReference.problem_reference_id)
        .where(
            (ProblemReference.group_id == group_id) &
            (ProblemReference.workbook_id == workbook_id) &
            (ProblemReference.problem_id == problem_id)
        )
        .limit(1)
    )
    res = await db.execute(q)
    return res.scalar_one_or_none()


async def accumulate_submission_time(
    db: AsyncSession,
    user_id: str,
    problem_reference_id: int,
    session_seconds: float,
    session_end: datetime | None = None,
):
    """
    동일 (user_id, problem_reference_id)에 대해 가장 최근 제출을 찾아
    total_solving_time(초 단위)에 session_seconds를 누적.

    - “가장 최근 제출” 기준은 created_at DESC.
    - 원하면 session_end 이전에 생성된 제출만 대상으로 제한할 수도 있음(주석 참고).
    - 동시성: FOR UPDATE로 레코드 잠그고 갱신.
    """
    # 최신 제출 1건 찾기
    subq = (
        select(Submission)
        .where(
            (Submission.user_id == user_id) &
            (Submission.problem_reference_id == problem_reference_id)
        )
        .order_by(Submission.created_at.desc())
        .limit(1)
        .with_for_update()  # 행 잠금으로 동시 누적 시 레이스 컨디션 방지
    )

    # session_end 이전 제출만 대상으로 하려면 아래 where 절 추가:
    # if session_end is not None:
    #     subq = subq.where(Submission.created_at <= session_end)

    result = await db.execute(subq)
    submission = result.scalars().first()
    if not submission:
        # 제출이 아직 없으면 스킵(또는 임시 버킷 테이블에 누적하고, 제출 생성 시 이월하는 전략도 가능)
        logger.info(
            f"[accumulate_submission_time] no submission yet (user_id={user_id}, ref={problem_reference_id}), skip accumulate"
        )
        return

    # 초 단위 부동소수 → 반올림 or 정수화 권장
    add_secs = max(0.0, float(session_seconds))
    current = submission.total_solving_time or 0.0
    submission.total_solving_time = float(current) + add_secs

    logger.debug(
        f"[accumulate_submission_time] submission_id={submission.submission_id}, "
        f"prev={current}, +{add_secs} => new={submission.total_solving_time}"
    )
#-----------------------------------------------------
def filter_none_values(d):
    return {k: v for k, v in d.items() if v is not None}

# --- API/통신/Redis는 schemas 기반 camelCase ---
async def add_presence(roomId, userId, sessionId, userData):
    # camelCase: userId, groupId 등 모든 key는 schemas와 완전 일치
    for raw in r.smembers(f"presence:{roomId}"):
        prevUid, prevSid = raw.split(":")
        if prevUid == userId and prevSid != sessionId:
            r.srem(f"presence:{roomId}", raw)
            r.delete(f"user_data:{prevUid}:{prevSid}")
    userData["active"] = "True"
    userData["createdAt"] = time.time()  # UNIX timestamp (camelCase for consistency)
    r.sadd(f"presence:{roomId}", f"{userId}:{sessionId}")
    r.hmset(f"user_data:{userId}:{sessionId}", userData) #페이지 새로고침,다중 접속 등 문제 방지

async def remove_presence(roomId, userId, sessionId, lastActivity=None):
    userData = r.hgetall(f"user_data:{userId}:{sessionId}")
    if userData:
        userData["active"] = "False"
        userData["disconnectedAt"] = time.time()
        if lastActivity:
            userData["lastActivity"] = lastActivity
        r.hmset(f"user_data:{userId}:{sessionId}", userData) #이탈/비활성 이력 기록, 후처리 일괄 동기화
        
async def get_presence(roomId):
    rawSessions = list(r.smembers(f"presence:{roomId}"))
    userIds = set()
    users = []
    logger.debug(f"[get_presence] rawSessions: {rawSessions}")
    print(f"[PRINT get_presence] rawSessions: {rawSessions}")
    for raw in rawSessions:
        try:
            uid, sid = raw.split(":")
            userData = r.hgetall(f"user_data:{uid}:{sid}")
            logger.debug(f"[get_presence] userData for {uid}:{sid}: {userData}")
            print(f"[PRINT get_presence] userData for {uid}:{sid}: {userData}")  
            if not userData or "active" not in userData:
                r.srem(f"presence:{roomId}", raw)
                r.delete(f"user_data:{uid}:{sid}")
                continue
            if userData.get("active") == "True":
                if uid not in userIds:
                    userIds.add(uid)
                    users.append(userData)
        except Exception as e:
            logger.error(f"[get_presence] 에러: {e}")
            print(f"[PRINT get_presence] 에러: {e}")
            r.srem(f"presence:{roomId}", raw)
            continue
    logger.info(f"[get_presence-return] userIds: {userIds}, users: {users}")
    print(f"[PRINT get_presence-return] userIds: {userIds}, users: {users}")
    return list(userIds), users #현재 접속 중인 활성 사용자만을 효율적으로 반환하는 함수

def parse_iso8601_naive(s):
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.replace(tzinfo=None)
    except Exception:
        return datetime.utcnow().replace(tzinfo=None)

# --- DB 저장은 models(UserSession, snake_case)로 매핑 ---
async def batch_sync_presence():
    now = time.time()
    roomKeys = r.keys("presence:*")
    for key in roomKeys:
        roomId = str(key).split(":")[1]  # e.g. "12/34/56" = group_id/workbook_id/problem_id
        rawSessions = list(r.smembers(f"presence:{roomId}"))
        async for db in get_db():
            db = cast(AsyncSession, db)

            # ★ 추가: page 파싱 → (group_id, workbook_id, problem_id)
            try:
                group_id_str, workbook_id_str, problem_id_str = roomId.split("/")
                group_id = int(group_id_str)
                workbook_id = int(workbook_id_str)
                problem_id = int(problem_id_str)
            except Exception:
                logger.warning(f"[batch_sync_presence] invalid page format: page={roomId}")
                continue

            # ★ 추가: page로 problem_reference_id 조회
            # - 스키마에 따라 조정 (아래는 예시)
            problem_reference_id = await get_problem_reference_id(db, group_id, workbook_id, problem_id)
            if problem_reference_id is None:
                logger.warning(f"[batch_sync_presence] problem_reference not found: page={roomId}")
                # 세션은 기록하되, submission 갱신은 Skip
                # continue  # ← 세션 기록을 계속하고 싶으면 주석 처리 유지

            for raw in rawSessions:
                try:
                    userId, sessionId = raw.split(":")
                    userData = r.hgetall(f"user_data:{userId}:{sessionId}")
                    logger.debug(f"[batch_sync_presence] userId={userId} sessionId={sessionId} userData={userData}")
                    print(f"[PRINT batch_sync_presence] userId={userId} sessionId={sessionId} userData={userData}")

                    if not userData or "active" not in userData:
                        r.srem(f"presence:{roomId}", raw)
                        r.delete(f"user_data:{userId}:{sessionId}")
                        continue

                    if userData.get("active") == "False":
                        disconnectedAt = float(userData.get("disconnectedAt", 0))
                        if now - disconnectedAt < 60:
                            continue

                        joinedAt = userData.get("joinedAt") or userData.get("createdAt")
                        lastActivity = userData.get("lastActivity") or userData.get("disconnectedAt")

                        if "T" in str(joinedAt):
                            t1 = parse_iso8601_naive(joinedAt)
                        else:
                            t1 = datetime.utcfromtimestamp(float(joinedAt)).replace(tzinfo=None)
                        if "T" in str(lastActivity):
                            t2 = parse_iso8601_naive(lastActivity)
                        else:
                            t2 = datetime.utcfromtimestamp(float(lastActivity)).replace(tzinfo=None)

                        sessionDuration = float((t2 - t1).total_seconds())

                        # 1) UserSession 기록 (기존 로직)
                        sessionData = {
                            "userId": userId,
                            "page": roomId,
                            "duration": sessionDuration,
                            "ipAddress": userData.get("ipAddress"),
                            "userAgent": userData.get("userAgent"),
                            "createdAt": t1,
                            "status": "inactive",
                        }
                        sessionObj = UserSessionCreate(**sessionData)
                        db_data = sessionObj.model_dump(by_alias=True)
                        print("db_data = ", db_data)

                        result = await db.execute(
                            select(UserSession).where(
                                (UserSession.user_id == db_data['user_id']) &
                                (UserSession.page == db_data['page']) &
                                (UserSession.created_at == db_data['created_at'])
                            )
                        )
                        record = result.scalars().first()
                        if record:
                            record.status = db_data['status']
                            record.duration = db_data['duration']
                            record.ip_address = db_data['ip_address']
                            record.user_agent = db_data['user_agent']
                        else:
                            record = UserSession(**db_data)
                            db.add(record)

                        # 2) ★ 추가: submission.total_solving_time에 세션 시간 누적
                        #    - 동일 user + problem_reference에 대해 "가장 최근 제출"을 찾아 duration 누적
                        if problem_reference_id is not None:
                            await accumulate_submission_time(
                                db=db,
                                user_id=userId,
                                problem_reference_id=problem_reference_id,
                                session_seconds=sessionDuration,
                                session_end=t2,          # 세션 종료 시각; 최신 제출 선택에 활용 가능
                            )

                        await db.commit()
                        logger.info(
                            f"session committed: user_id={db_data['user_id']}, page={db_data['page']}, created_at={db_data['created_at']}"
                        )

                        # 3) Redis 청소
                        r.srem(f"presence:{roomId}", raw)
                        r.delete(f"user_data:{userId}:{sessionId}")
                except Exception as e:
                    logger.error(f"batch_sync_presence error: {e}")
                    print(f"[PRINT batch_sync_presence error] {e}")
                    r.srem(f"presence:{roomId}", raw)
                    r.delete(f"user_data:{userId}:{sessionId}")
                    continue # Redis의 presence 데이터를 주기적으로 PostgreSQL DB에 동기화하고, 동기화 후 Redis에서 해당 세션 정보를 삭제하는 역할

async def scheduled_job():
    while True:
        await batch_sync_presence()
        await asyncio.sleep(60)  # 1시간마다 실행
