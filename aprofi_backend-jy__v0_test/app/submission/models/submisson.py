# app/submission/models/submisson.py
from __future__ import annotations

from typing import Any
from datetime import datetime

from sqlalchemy import Integer, String, DateTime, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base
from app.user.models.User import User
from app.problem_ref.models.problem_ref import ProblemReference


class Submission(Base):
    __tablename__ = "submissions"

    submission_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    user_id: Mapped[str] = mapped_column(
        String,
        ForeignKey(f"{User.__tablename__}.user_id"),
        nullable=False,
    )
    problem_reference_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(f"{ProblemReference.__tablename__}.problem_reference_id"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    submission_type: Mapped[str] = mapped_column(String, nullable=False)
    total_solving_time: Mapped[float | None] = mapped_column(Float, default=None, nullable=True)

    __mapper_args__ = {
        "polymorphic_on": submission_type,
        "polymorphic_identity": "base",
    }

    # 임시 필드 (꼭 필요한 것만 남기세요 — 불필요하면 지우는 게 최선)
    temporary_field_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    temporary_table_link: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 나머지 임시 int/str/datetime 필드가 정말 필요하면 아래처럼 추가
    # temporary_field_int_1: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # temporary_field_str_1: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # temporary_field_datetime_1: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
