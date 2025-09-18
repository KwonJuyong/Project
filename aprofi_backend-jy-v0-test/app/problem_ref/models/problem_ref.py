# 그룹 / 문제지 / 문제를 엮는 모델

from datetime import datetime
from sqlalchemy import Integer, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base

class ProblemReference(Base):
    """문제 참조 모델
    이 모델은 문제와 그룹, 문제지 간의 관계를 정의합니다.
    각 문제는 특정 그룹에 속하며, 문제지는 여러 문제를 포함할 수 있습니다.
    """
    
    __tablename__ = "problem_reference"

    problem_reference_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    problem_id: Mapped[int] = mapped_column(Integer, ForeignKey("problem.problem_id"), nullable=False)
    group_id: Mapped[int] = mapped_column(Integer, ForeignKey("group.group_id"), nullable=False)
    workbook_id: Mapped[int] = mapped_column(Integer, ForeignKey("workbook.workbook_id"), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, nullable=True)

    points: Mapped[float | None] = mapped_column(Float, default=None, nullable=True)  # 문제에 대한 점수 (선택적)