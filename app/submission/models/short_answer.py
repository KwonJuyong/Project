from sqlalchemy import Integer, Boolean, ForeignKey, ARRAY, String
from sqlalchemy.orm import Mapped, mapped_column
from app.submission.models.submisson import Submission
from sqlalchemy.types import Enum as SQLEnum
from app.problem.models.short_answer_problem import ShortAnswerRatingMode

class ShortAnswerSubmission(Submission):
    __tablename__ = "short_answer_submission"

    submission_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("submissions.submission_id"), primary_key=True
    )

    # 제출한 답변 목록
    answer: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=lambda: [], nullable=False
    )

    # 정답 여부
    is_correct: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    
    __mapper_args__ = {
        "polymorphic_identity": "short_answer",
        "with_polymorphic": "*"
    }