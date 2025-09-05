from __future__ import annotations
from typing import Annotated
from datetime import timezone
from typing import List
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.security import get_current_user

from app.submission.schemas import (
    SolveRequestUnion, SolveResponse, ProblemTypeKOR, SolveResponseUnionMe, RunCodeRequest, RunCodeResponse, SubmissionScoreResponse, SubmissionScoreCreateRequest, getAllSubmissionsResponse, SubmissionGetScoreResponse
)
from app.submission.crud.submission import SolveService, list_solves_me, run_code_and_log, create_submission_score_crud, list_latest_submission_summaries_crud, list_scores_by_submission_id
from app.submission.models.submission_score import SubmissionScore


router = APIRouter(prefix="/solves")

@router.post("", response_model=SolveResponse, status_code=status.HTTP_201_CREATED)
async def create_solve(
    payload: SolveRequestUnion,
    group_id: int = Query(..., ge=1),
    workbook_id: int = Query(..., ge=1),
    problem_id: int = Query(..., ge=1),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    문제 유형별 채점 → 서브미션 저장 → 통일된 응답 반환.
    """
    user_id = current_user["sub"]

    # 유효성
    if payload.problemType not in ProblemTypeKOR:
        raise HTTPException(status_code=400, detail="INVALID_PROBLEM_TYPE")

    service = SolveService(db=db, current_user=current_user)
    result = await service.grade_and_save(
        payload=payload,
        user_id=user_id,
        group_id=group_id,
        workbook_id=workbook_id,
        problem_id=problem_id,
    )

    return SolveResponse(
        solve_id=result.submission_id,
        problem_id=result.problem_id,
        user_id=user_id,
        submitted_at=result.created_at.replace(tzinfo=timezone.utc).isoformat(),
        result="correct" if result.is_correct else "wrong",
    )
    
@router.get("/me", response_model=List[SolveResponseUnionMe],
    status_code=status.HTTP_200_OK,
    summary="제출 목록 조회 (SolveResponseUnionMe)",
)
async def get_solves(
    user_id: Optional[str] = Query(default=None, description="특정 사용자로 필터"),
    group_id: Optional[int] = Query(default=None, description="그룹 ID로 필터"),
    workbook_id: Optional[int] = Query(default=None, description="워크북 ID로 필터"),
    problem_id: Optional[int] = Query(default=None, description="문제 ID로 필터"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    SolveResponseUnionMe 스키마로 제출 이력을 반환합니다.
    - 코딩/디버깅: `code_language`, `code_len` 포함
    - 나머지 유형: 공통 필드만
    """
    return await list_solves_me(
        db,
        user_id=user_id,
        group_id=group_id,
        workbook_id=workbook_id,
        problem_id=problem_id,
        limit=limit,
        offset=offset,
    )
    
@router.post(
    "/run_code",
    response_model=RunCodeResponse,
    status_code=status.HTTP_200_OK,
    summary="테스트케이스로 코드 실행 (로그 저장 포함)"
)
async def run_code_endpoint(
    payload: RunCodeRequest,
    user_id: str = Query(..., description="로그 저장을 위한 사용자 ID"),
    problem_reference_id: int = Query(..., description="로그 저장 대상 문제 참조 ID"),
    db: AsyncSession = Depends(get_db),
) -> RunCodeResponse:
    """
    프론트 요청(Request/Response 예시)에 맞춰 동작.
    - body: RunCodeRequest
      - language, code, rating_mode, test_cases(or testcases)
    - query: user_id, problem_reference_id (DB 로그 저장을 위해 필수)
    """
    if not user_id or problem_reference_id is None:
        raise HTTPException(status_code=400, detail="user_id and problem_reference_id are required")

    resp = await run_code_and_log(
        db=db,
        body=payload,
        user_id=user_id,
        problem_reference_id=problem_reference_id,
    )
    # 트랜잭션 커밋 (CRUD에서 flush만 수행)
    await db.commit()
    return resp

@router.post("/grading/{solve_id}/score", response_model=SubmissionScoreResponse)
async def create_submission_score(
    solve_id: int,
    payload: SubmissionScoreCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    - path: solve_id (= submission_id)
    - body: score, prof_feedback
    - graded_by: current_user에서 추출
    """
    graded_by = (
        str(current_user.get("user_id"))
        if isinstance(current_user, dict) and current_user.get("user_id")
        else "unknown"
    )

    sc: SubmissionScore = await create_submission_score_crud(
        db=db,
        submission_id=solve_id,
        score=payload.score,
        prof_feedback=payload.prof_feedback,
        graded_by=graded_by,
    )

    await db.commit()

    return SubmissionScoreResponse(
        submission_score_id=sc.submission_score_id,
        submission_id=sc.submission_id,
        score=sc.score,
        prof_feedback=sc.prof_feedback or "",
        graded_by=sc.graded_by or "",
        created_at=sc.created_at,
    )
    
@router.get("/groups/{group_id}/workbooks/{workbook_id}/problems/{problem_id}/submissions", response_model=List[getAllSubmissionsResponse])
async def list_latest_submission_summaries(
    group_id: int,
    workbook_id: int,
    problem_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # 공개 API라면 이 줄 제거
):
    """
    - 같은 문제에 대해 여러 번 제출한 경우:
      * submission_id: 가장 최신(가장 큰) 제출 ID
      * created_at: 그 문제의 첫 제출 시간(가장 작은 submission_id의 created_at)
      * updated_at: 최신 제출 시간(가장 큰 submission_id의 created_at)
      * score: 최신 제출에 연결된 가장 최근 점수 (없으면 null)
      * reviewed: score가 존재하면 true, 없으면 false
    """
    user_id = current_user["sub"]
    items = await list_latest_submission_summaries_crud(
        db,
        user_id=user_id,
        group_id=group_id,
        workbook_id=workbook_id,
        problem_id=problem_id,
    )
    return items

@router.get(
    "/{submission_id}/scores",
    response_model=List[SubmissionGetScoreResponse],
    status_code=status.HTTP_200_OK,
    summary="특정 제출의 채점 기록 조회 (is_deleted=false)",
)
async def get_submission_scores(
    submission_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    특정 제출(submission_id)의 채점 기록(점수 + 채점자)을 모두 조회합니다.
    - is_deleted = false 인 행만 반환
    - created_at 오름차순 정렬
    """
    items = await list_scores_by_submission_id(db=db, submission_id=submission_id)
    return items

