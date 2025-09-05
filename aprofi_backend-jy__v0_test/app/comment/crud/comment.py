from typing import List
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from fastapi import HTTPException

from app.comment.models.comment import Comment
from app.comment.schemas import CommentCreateRequest, CommentCreateResponse, CommentGetProblemResponse, CommmentGetSolveResponse, AIFeedbackResponse

async def create_comment(db: AsyncSession, payload: CommentCreateRequest) -> Comment:
    problem_id = payload.problem_id
    submission_id = payload.solve_id

    # '하나 이상'만 요구: 둘 다 None이면 에러
    if problem_id is None and submission_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of problem_id or solve_id is required."
        )

    # 플래그는 존재 여부로 자동 결정 (is_problem_message는 힌트로만 사용)
    is_problem_comment = (problem_id is not None) or bool(payload.is_problem_message)
    is_submission_comment = (submission_id is not None)

    # 둘 다 있는 경우: is_problem_message와 상관없이 두 플래그 모두 True
    #    (원하면 여기에 경고/로그만 남기고 허용)

    obj = Comment(
        maker_id=payload.user_id,
        is_problem_comment=is_problem_comment,
        problem_id=problem_id if is_problem_comment else None,
        is_submission_comment=is_submission_comment,
        submission_id=submission_id if is_submission_comment else None,
        content=payload.comment,
    )

    db.add(obj)
    await db.flush()
    return obj


def to_response_model(obj: Comment) -> CommentCreateResponse:
    """ORM -> Response 스키마로 변환 (키 이름 맞춰 매핑)"""
    return CommentCreateResponse(
        comment_id=obj.comment_id,
        user_id=obj.maker_id,
        problem_id=obj.problem_id,
        solve_id=obj.submission_id,
        comment=obj.content,
        is_problem_message=obj.is_problem_comment,
        created_at=obj.created_at,
    )
    
#___________________________________________________________________________

def to_problem_response(obj: Comment) -> CommentGetProblemResponse:
    return CommentGetProblemResponse(
        comment_id=obj.comment_id,
        user_id=obj.maker_id,
        problem_id=obj.problem_id,
        solve_id=obj.submission_id,
        comment=obj.content,
        is_problem_message=obj.is_problem_comment,
        timestamp=obj.created_at,
    )


async def get_comments_by_problem(db: AsyncSession, problem_id: int) -> List[CommentGetProblemResponse]:
    stmt = (
        select(Comment)
        .where(
            and_(
                Comment.problem_id == problem_id,
                Comment.is_deleted.is_(False),
                Comment.is_problem_comment.is_(True),
            )
        )
        .order_by(Comment.created_at.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [to_problem_response(row) for row in rows]

#___________________________________________________________________________
def to_solve_response(obj: Comment) -> CommmentGetSolveResponse:
    return CommmentGetSolveResponse(
        comment_id=obj.comment_id,
        user_id=obj.maker_id,
        problem_id=obj.problem_id,
        solve_id=obj.submission_id,
        comment=obj.content,
        is_problem_message=obj.is_problem_comment,
        timestamp=obj.created_at,
    )
    
async def get_comments_by_submission(db: AsyncSession, solve_id: int) -> List[CommmentGetSolveResponse]:
    stmt = (
        select(Comment)
        .where(
            and_(
                Comment.submission_id == solve_id,
                Comment.is_deleted.is_(False),
                Comment.is_submission_comment.is_(True),
            )
        )
        .order_by(Comment.created_at.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [to_solve_response(row) for row in rows]


#___________________________________________________________________________
