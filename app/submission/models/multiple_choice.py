from sqlalchemy import Integer, Boolean, ForeignKey, ARRAY, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.submission.models.submisson import Submission
from datetime import datetime
from sqlalchemy.sql import func

class MultipleChoiceSubmission(Submission):
    __tablename__ = "multiple_choice_submission"

    submission_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("submissions.submission_id"), primary_key=True
    )

    # 사용자가 선택한 선택지 인덱스 또는 값 (정답과 비교용)
    selected_option_indices: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False
    )

    # 정답 여부
    is_correct: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __mapper_args__ = {
        "polymorphic_identity": "multiple_choice",
        "with_polymorphic": "*"
    }