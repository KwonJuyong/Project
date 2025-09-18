from app.database import Base
from sqlalchemy import Integer, String, DateTime, Boolean, ForeignKey, Float, Text
from sqlalchemy.dialects.postgresql import JSONB  
from sqlalchemy.sql import func
from sqlalchemy.orm import Mapped, mapped_column
from typing import Any, Dict, List, Optional
from datetime import datetime

class CodingSubmissionLog(Base):
    __tablename__ = "coding_submission_log"
    coding_submission_log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(Integer, ForeignKey("submissions.submission_id"), nullable=False)
    code_by_enter: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)