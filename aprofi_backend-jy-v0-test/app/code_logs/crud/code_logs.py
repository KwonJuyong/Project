from typing import List, Any, Dict, Union
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, or_, cast
from sqlalchemy.sql import and_
from sqlalchemy.dialects.postgresql import JSONB
from fastapi import HTTPException
from app.submission.models.submisson import Submission
from app.code_logs.schemas import CodeLogsRequest, CodeLogsResponse
from app.code_logs.models.coding_submission_log import CodingSubmissionLog
from app.submission.models.coding import CodingSubmission
from app.submission.models.testcases_excution_log import TestcasesExecutionLog


def _to_dt(x: Union[str, datetime]) -> datetime:
    return x if isinstance(x, datetime) else datetime.fromisoformat(x)

def _is_empty_text_array(col):
    # NULL 이거나 빈 배열이면 True
    return or_(col.is_(None), func.coalesce(func.array_length(col, 1), 0) == 0)

async def code_logs_create_crud(db: AsyncSession, payload: CodeLogsRequest) -> int:
    # 0) 길이 검증
    if len(payload.code_logs) != len(payload.timestamp):
        raise ValueError("code_logs and timestamp length mismatch")

    # 1) 제출 존재 + user_id 확보
    sub_row = await db.execute(
        select(Submission.submission_id, Submission.user_id)
        .where(Submission.submission_id == payload.solve_id)
    )
    sub = sub_row.first()
    if sub is None:
        raise HTTPException(status_code=404, detail="SUBMISSION_NOT_FOUND")
    submission_id, user_id = sub

    # 2) 로그 insert
    logs = [
        CodingSubmissionLog(
            submission_id=submission_id,
            code_by_enter=c,
            created_at=_to_dt(t),
        )
        for c, t in zip(payload.code_logs, payload.timestamp)
    ]
    db.add_all(logs)
    await db.flush()  # PK 부여

    # 3) 최신 로그 1건 가져오기 (같은 submission_id)
    latest_log_row = await db.execute(
        select(CodingSubmissionLog.code_by_enter)
        .where(CodingSubmissionLog.submission_id == submission_id)
        .order_by(
            desc(CodingSubmissionLog.created_at),
            desc(CodingSubmissionLog.coding_submission_log_id),
        )
        .limit(1)
    )
    latest_code = latest_log_row.scalar_one_or_none()
    if latest_code is None:
        return len(logs)

    # 4) 우선순위 A: 같은 submission_id의 CodingSubmission 중 빈 슬롯 1건
    cs_same_sub_row = await db.execute(
        select(CodingSubmission)
        .where(CodingSubmission.submission_id == submission_id)
        .where(_is_empty_text_array(CodingSubmission.submission_code_log))
        .limit(1)  # 1:1 구조라 정렬 불필요
    )
    cs_target = cs_same_sub_row.scalars().first()

    # 5) 우선순위 B: 같은 유저의 다른 제출 중 빈 슬롯 "최신" 1건
    if cs_target is None:
        cs_user_row = await db.execute(
            select(CodingSubmission)
            .join(Submission, Submission.submission_id == CodingSubmission.submission_id)
            .where(Submission.user_id == user_id)
            .where(_is_empty_text_array(CodingSubmission.submission_code_log))
            .order_by(
                desc(Submission.created_at),          # 최신 제출 우선
                desc(CodingSubmission.submission_id), # 2차 키
            )
            .limit(1)
        )
        cs_target = cs_user_row.scalars().first()

    # 6) 타겟이 있으면 최신 code_by_enter를 TEXT[] 형태로 저장
    if cs_target is not None:
        cs_target.submission_code_log = [latest_code]  # TEXT[] 컬럼
        await db.flush()

    return len(logs)

async def code_logs_get_by_solve_id_crud(db: AsyncSession, solve_id: int) -> List[Dict[str, Any]]:
    """
    주어진 solve_id(=submission_id)의 코드 입력 로그만 반환.
    반환 형식:
    [
      {"code": "...", "timestamp": "..."},
      {"code": "...", "timestamp": "..."}
    ]
    """
    result = await db.execute(
        select(CodingSubmissionLog)
        .where(CodingSubmissionLog.submission_id == solve_id)
        .order_by(CodingSubmissionLog.created_at.asc())
    )
    logs = result.scalars().all()

    return [
        {
            "code": r.code_by_enter,
            "timestamp": r.created_at.isoformat()  # datetime → ISO8601 string
        }
        for r in logs
    ]