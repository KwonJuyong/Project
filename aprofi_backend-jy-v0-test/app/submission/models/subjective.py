from sqlalchemy import Integer, Boolean, ForeignKey, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.submission.models.submisson import Submission
from sqlalchemy.types import Enum as SQLEnum

from app.problem.models.subjective_problem import AutoRatingMode


class SubjectiveSubmission(Submission):
    __tablename__ = "subjective_submission"

    submission_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("submissions.submission_id"), primary_key=True
    )

    # 사용자의 주관식 서술 답변
    answer: Mapped[str] = mapped_column(String, nullable=False)
    
    # 정답 여부
    is_correct: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    
    __mapper_args__ = {
        "polymorphic_identity": "subjective",
        "with_polymorphic": "*"
    }