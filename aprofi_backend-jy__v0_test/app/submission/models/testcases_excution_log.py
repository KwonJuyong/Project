from datetime import datetime

from sqlalchemy import Integer, String, DateTime, ForeignKey, Float, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.types import Enum as SQLEnum
from typing import List


from enum import Enum as PyEnum
from app.database import Base
from app.user.models.User import User
from app.problem_ref.models.problem_ref import ProblemReference

class languageEnum(PyEnum):
    python = "python"
    javascript = "javascript"
    java = "java"
    cpp = "cpp"
    etc = "etc"
    c = "c"

class TestcasesExecutionLog(Base):
    __tablename__ = "test_cases_execution_logs"

    code_execution_log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey(f"{User.__tablename__}.user_id"), nullable=False)
    problem_reference_id: Mapped[int] = mapped_column(Integer, ForeignKey(f"{ProblemReference.__tablename__}.problem_reference_id"), nullable=False)
    code : Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(SQLEnum(languageEnum), nullable=False)
    sample_test_cases_results: Mapped[list[dict | None]] = mapped_column(JSONB, default=list, nullable=False)
    user_test_case_results:   Mapped[list[dict | None]] = mapped_column(JSONB, default=list, nullable=False)
    memory_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_error: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    running_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_details: Mapped[list[dict | None]] = mapped_column(JSONB, default=list, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)