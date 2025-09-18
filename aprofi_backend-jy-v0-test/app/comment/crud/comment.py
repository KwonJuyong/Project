from typing import List, Dict, Any, Optional, Tuple
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, update
from fastapi import HTTPException
import logging
from app.comment.models.comment import Comment
from app.comment.schemas import CommentCreateRequest, CommentCreateResponse, CommentGetProblemResponse, CommmentGetSolveResponse, AIFeedbackResponse
from app.submission.models.submisson import Submission
from app.submission.models.submission_score import SubmissionScore
from app.problem_ref.models.problem_ref import ProblemReference
from app.comment.schemas import ConditionResult, ConditionStatus, OverallStatus

logger = logging.getLogger(__name__)


async def create_comment(db: AsyncSession, payload: CommentCreateRequest) -> Comment:
    problem_id = payload.problem_id
    submission_id = payload.solve_id

    # 1) 최소 요건: 둘 다 None이면 에러
    if problem_id is None and submission_id is None and payload.is_problem_message is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of problem_id or solve_id is required."
        )

    # 2) 우선순위: is_problem_message 힌트가 있으면 그대로 강제 (상호 배타)
    #    True  → 문제 코멘트,  False → 제출 코멘트
    if payload.is_problem_message is True:
        is_problem_comment = True
        is_submission_comment = False
    elif payload.is_problem_message is False:
        is_problem_comment = False
        is_submission_comment = True
    else:
        # 3) 힌트가 없으면 ID 존재로 추론 (역시 상호 배타)
        if submission_id is not None and problem_id is None:
            is_problem_comment = False
            is_submission_comment = True
        elif problem_id is not None and submission_id is None:
            is_problem_comment = True
            is_submission_comment = False
        elif problem_id is not None and submission_id is not None:
            # 둘 다 있을 때의 기본 정책: 제출 코멘트로 간주(요구 “각각 달라”를 반영하여 동시 True 금지)
            logger.info("Both problem_id and submission_id provided; defaulting to submission comment")
            is_problem_comment = False
            is_submission_comment = True
        else:
            # 방어: 이 경우는 1)에서 걸러지지만 혹시 모를 케이스
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one of problem_id or solve_id is required."
            )

    # 4) 선택된 유형에 필수 ID가 없는 경우 명확히 에러 처리
    if is_problem_comment and problem_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="problem_id is required when is_problem_message is True."
        )
    if is_submission_comment and submission_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="solve_id is required when is_problem_message is False."
        )

    # 5) Comment 생성 (선택되지 않은 쪽의 ID는 None으로 저장)
    obj = Comment(
        maker_id=payload.user_id,
        is_problem_comment=is_problem_comment,
        problem_id=problem_id if is_problem_comment else None,
        is_submission_comment=is_submission_comment,
        submission_id=submission_id if is_submission_comment else None,
        content=payload.comment,
    )

    db.add(obj)
    await db.flush()   # PK 할당
    await db.refresh(obj)
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
# =========================
# 저장(선택) — 필요 시 사용
# =========================
async def save_condition_results(
    db: AsyncSession,
    *,
    submission_id: int,
    condition_results: List[Dict[str, Any]],
) -> None:
    """
    Submission.condition_check_results(JSONB)에 ConditionResult[] 저장.
    딕셔너리 포맷 예:
      {
        "condition_id": 1,
        "condition": "...",
        "status": "pass" | "fail",
        "description": "...",
        "feedback": "...",
        "score": 10.0
      }
    """
    stmt = (
        update(Submission)
        .where(Submission.submission_id == submission_id)
        .values(condition_check_results=condition_results)
    )
    await db.execute(stmt)


async def save_ai_feedback_score(
    db: AsyncSession,
    *,
    submission_id: int,
    score: float,
    ai_feedback: Optional[str],
    graded_by: Optional[str] = None,
) -> SubmissionScore:
    """
    SubmissionScore에 AI 점수/피드백을 새 행으로 저장.
    (네가 이미 별도의 _persist_score를 쓰면 그걸 그대로 사용해도 됨)
    """
    row = SubmissionScore(
        submission_id=submission_id,
        score=float(score),
        ai_feedback=(ai_feedback or ""),
        graded_by=(graded_by or "AI"),
    )
    db.add(row)
    await db.flush()
    return row


# =========================
# 읽기 — GET 라우터용
# =========================
async def build_ai_feedback_response(
    db: AsyncSession,
    *,
    submission_id: int
) -> Optional[AIFeedbackResponse]:
    """
    단일 submission_id에 대한 AIFeedbackResponse를 조합하여 반환.
    - points: ProblemReference의 score/points/max_points 중 존재하는 필드, 없으면 100
    - total_score/ai_feedback: 최신 SubmissionScore(삭제 아님, 최신 created_at)
    - condition_results: Submission.condition_check_results(JSONB) → ConditionResult[]
    - all_status: 모든 조건 status='pass'면 success, 아니면 fail (조건 없으면 success)
    """
    sub, score_row, pref = await _fetch_submission_bundle(db, submission_id)
    if sub is None:
        return None

    points = _extract_points(pref)
    cond_list = _as_condition_result_list(getattr(sub, "condition_check_results", None))
    overall = _compute_overall_status(cond_list)

    total_score = float(getattr(score_row, "score", 0.0)) if score_row else 0.0
    ai_fb_raw = getattr(score_row, "ai_feedback", "") if score_row else ""
    ai_fb = "" if (ai_fb_raw is None or str(ai_fb_raw).strip().lower() == "null") else str(ai_fb_raw)

    return AIFeedbackResponse(
        solve_id=int(sub.submission_id),
        ai_feedback=ai_fb,
        total_score=round(total_score, 2),
        points=round(points, 2),
        condition_results=cond_list,
        all_status=overall,
    )


# =========================
# 내부 헬퍼
# =========================
async def _fetch_submission_bundle(
    db: AsyncSession,
    submission_id: int
) -> Tuple[Optional[Submission], Optional[SubmissionScore], Optional[ProblemReference]]:
    """Submission + 최신 SubmissionScore + ProblemReference를 한 번에 로드"""
    sub = await db.scalar(
        select(Submission).where(Submission.submission_id == submission_id)
    )
    if sub is None:
        return None, None, None

    score_row = await db.scalar(
        select(SubmissionScore)
        .where(
            SubmissionScore.submission_id == submission_id,
            SubmissionScore.is_deleted == False,  # noqa: E712
        )
        .order_by(desc(SubmissionScore.created_at))
        .limit(1)
    )

    pref = await db.scalar(
        select(ProblemReference).where(
            ProblemReference.problem_reference_id == sub.problem_reference_id
        )
    )
    return sub, score_row, pref


def _extract_points(pref: Optional[ProblemReference]) -> float:
    """
    배점 컬럼 후보: score | points | max_points
    """
    if pref is None:
        return 100.0
    for field in ("score", "points", "max_points"):
        if hasattr(pref, field):
            val = getattr(pref, field)
            try:
                if val is not None:
                    return float(val)
            except Exception:
                continue
    return 100.0


def _as_condition_result_list(
    raw: Optional[List[Dict[str, Any]]]
) -> List[ConditionResult]:
    """
    DB JSONB(raw)를 엄격한 ConditionResult 리스트로 변환.
    - 과거 포맷(passed: bool)도 흡수하여 status로 매핑
    - 필수 키가 없으면 기본값으로 보정
    """
    raw = raw or []
    out: List[ConditionResult] = []
    for i, item in enumerate(raw, 1):
        # status 우선, 없으면 passed → status 변환
        status_val = item.get("status")
        if status_val is None:
            status_val = "pass" if (item.get("passed") is True) else "fail"
        try:
            status_enum = ConditionStatus(status_val)
        except Exception:
            status_enum = ConditionStatus.FAIL

        cond_id = int(item.get("condition_id", i))
        condition = str(item.get("condition") or item.get("description") or "")
        description = str(item.get("description") or item.get("condition") or "")
        feedback = str(item.get("feedback") or "")
        try:
            score = float(item.get("score", 0.0))
        except Exception:
            score = 0.0

        out.append(ConditionResult(
            condition_id=cond_id,
            condition=condition,
            status=status_enum,
            description=description,
            feedback=feedback,
            score=score,
        ))
    return out


def _compute_overall_status(conds: List[ConditionResult]) -> OverallStatus:
    """
    조건이 하나도 없으면 SUCCESS, 하나라도 fail이면 FAIL.
    (필수/선택 정보가 따로 없다면 모두 필수로 간주)
    """
    if not conds:
        return OverallStatus.SUCCESS
    return OverallStatus.SUCCESS if all(c.status == ConditionStatus.PASS for c in conds) else OverallStatus.FAIL
