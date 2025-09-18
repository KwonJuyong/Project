# app/user_session/models/user_session.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import String, Float, DateTime, Integer, Index, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserSession(Base):
    __tablename__ = "user_sessions"

    # 기본키
    user_session_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 식별자/컨텍스트
    user_id: Mapped[str] = mapped_column(String, ForeignKey("user.user_id"), nullable=False)
    page: Mapped[str] = mapped_column(String(255), index=True, nullable=False)

    # 상태/지표
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="inactive")  # "active"/"inactive"
    duration: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)          # seconds

    # 메타
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    # 타임스탬프
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        # 중복 방지/조회 최적화 용도: 필요에 맞게 unique 여부 조정
        Index("ix_usersession_user_page_created", "user_id", "page", "created_at"),
    )
