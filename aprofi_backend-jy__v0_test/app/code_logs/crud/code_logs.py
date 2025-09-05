from typing import List, Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.sql import and_
from fastapi import HTTPException
from app.submission.models.submisson import Submission
from app.code_logs.schemas import CodeLogsRequest, CodeLogsResponse
from app.code_logs.models.coding_submission_log import CodingSubmissionLog
from app.submission.models.testcases_excution_log import TestcasesExecutionLog


async def code_logs_create_crud(db: AsyncSession, payload: CodeLogsRequest) -> int:
    if len(payload.code_logs) != len(payload.timestamp):
        raise ValueError("code_logs and timestamp length mismatch")

    # 1) FK 대상 제출 존재 확인
    exists_row = await db.execute(
        select(Submission.submission_id)
        .where(Submission.submission_id == payload.solve_id)
    )
    exists = exists_row.scalar_one_or_none()
    if not exists:
        # 존재하는 submission_id를 보내지 않으면 FK 에러가 납니다.
        raise HTTPException(status_code=404, detail="SUBMISSION_NOT_FOUND")

    # 2) 존재하면 로그 insert
    logs = [
        CodingSubmissionLog(
            submission_id=payload.solve_id,
            code_by_enter=c,
            created_at=t,
        )
        for c, t in zip(payload.code_logs, payload.timestamp)
    ]
    db.add_all(logs)
    await db.flush()   # PK 배정

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