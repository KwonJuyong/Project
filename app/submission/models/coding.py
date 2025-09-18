from __future__ import annotations
from enum import Enum as PyEnum

from sqlalchemy import Integer, Boolean, ForeignKey, String, Float, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import Enum as SQLEnum

from app.submission.models.submisson import Submission
from app.problem.models.subjective_problem import AutoRatingMode

class ExecutionStatus(str, PyEnum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    ERROR   = "ERROR"


class CodingSubmission(Submission):
    __tablename__ = "coding_submission"

    submission_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("submissions.submission_id"), primary_key=True
    )

    submission_code_log: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    submission_code: Mapped[str] = mapped_column(String, nullable=False)
    submission_language: Mapped[str] = mapped_column(String, nullable=False)

    execution_status: Mapped[ExecutionStatus] = mapped_column(
        SQLEnum(ExecutionStatus), nullable=False, default=ExecutionStatus.PENDING
    )
    execution_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)

    auto_rating_mode: Mapped[AutoRatingMode] = mapped_column(
        SQLEnum(AutoRatingMode), nullable=False, default=AutoRatingMode.deactive
    )
    auto_rating_criteria: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    user_test_case_results:   Mapped[list[dict | None]] = mapped_column(JSONB, default=list, nullable=False)

    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "coding",
        "with_polymorphic": "*",
    }


class DebuggingSubmission(Submission):  # 부모를 Submission으로 변경 (형제 관계)
    __tablename__ = "debugging_submission"

    submission_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("submissions.submission_id"), primary_key=True
    )

    # 코딩과 동일한 스키마를 쓴다면 그대로 복제 (또는 Mixin으로 공통화)
    submission_code_log: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    submission_code: Mapped[str] = mapped_column(String, nullable=False)
    submission_language: Mapped[str] = mapped_column(String, nullable=False)

    execution_status: Mapped[ExecutionStatus] = mapped_column(
        SQLEnum(ExecutionStatus), nullable=False, default=ExecutionStatus.PENDING
    )
    execution_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)

    auto_rating_mode: Mapped[AutoRatingMode] = mapped_column(
        SQLEnum(AutoRatingMode), nullable=False, default=AutoRatingMode.deactive
    )
    auto_rating_criteria: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    user_test_case_results:   Mapped[list[dict | None]] = mapped_column(JSONB, default=list, nullable=False)

    error_message: Mapped[str | None] = mapped_column(String, nullable=True)

    __mapper_args__ = {
        "polymorphic_identity": "debugging",
        "with_polymorphic": "*",
    }