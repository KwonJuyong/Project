# app/submission/models/submission_score.py
from __future__ import annotations

from datetime import datetime
from sqlalchemy import Integer, String, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base

class SubmissionScore(Base):
    __tablename__ = "submission_scores"

    submission_score_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(Integer, ForeignKey("submissions.submission_id"), nullable=False)
    prof_feedback: Mapped[str | None] = mapped_column(String, nullable=True, default="null")
    ai_feedback: Mapped[str | None] = mapped_column(String, nullable=True, default="null")
    score: Mapped[float] = mapped_column(Float, nullable=False)
    graded_by: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None, nullable=True)
