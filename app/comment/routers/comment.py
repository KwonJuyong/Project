from typing import List
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.security import get_current_user
from app.comment.schemas import CommentCreateRequest, CommentCreateResponse, CommentGetProblemResponse, CommmentGetSolveResponse, AIFeedbackResponse
from app.comment.crud.comment import (
    create_comment, to_response_model, get_comments_by_problem, get_comments_by_submission, build_ai_feedback_response
)

router = APIRouter(prefix="/comments")

@router.post(
    "",
    response_model=CommentCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="코멘트 생성 (문제/제출 중 하나에 달기)"
)
async def comment_create(
    payload: CommentCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    # 스키마에 user_id가 포함되어 있으므로 토큰 사용 없이 그대로 저장
    obj = await create_comment(db, payload)
    await db.commit()
    return to_response_model(obj)


@router.get("/problem_id/{problem_id}", response_model=List[CommentGetProblemResponse])
async def comments_get_by_problem(
    problem_id: int, 
    db: AsyncSession = Depends(get_db), 
    current_user=Depends(get_current_user)
    ):
    return await get_comments_by_problem(db, problem_id)

@router.get("/solve_id/{solve_id}", response_model=List[CommmentGetSolveResponse])
async def comments_get_by_solve(
    solve_id: int, 
    db: AsyncSession = Depends(get_db), 
    current_user=Depends(get_current_user)):
    return await get_comments_by_submission(db, solve_id)

@router.get("/ai_feedback/{solve_id}", response_model=AIFeedbackResponse)
async def read_ai_feedback_only(
    solve_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    실행/생성 없이 DB에서 'solve_id(submission_id)'에 대한
    AI 피드백/점수/조건결과를 읽어 AIFeedbackResponse로 반환.
    """
    resp = await build_ai_feedback_response(db, submission_id=solve_id)
    if resp is None:
        raise HTTPException(status_code=404, detail="SUBMISSION_NOT_FOUND")
    return resp