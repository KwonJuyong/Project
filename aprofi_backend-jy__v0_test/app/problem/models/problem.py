from datetime import datetime
from sqlalchemy import Integer, String, DateTime, Boolean, ARRAY, ForeignKey, Text, Float
from enum import Enum as PyEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from typing import Dict
from sqlalchemy import Enum as SQLEnum

from app.database import Base

class ProblemTypeEnum(str, PyEnum):
    coding = "coding"
    multiple_choice = "multiple_choice"
    short_answer = "short_answer"
    subjective = "subjective"
    debugging = "debugging"

class Problem(Base):
    __tablename__ = "problem"

    problem_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    maker_id: Mapped[str] = mapped_column(String, ForeignKey("user.user_id"), nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    difficulty: Mapped[str] = mapped_column(String, nullable=False)
    problem_type: Mapped[ProblemTypeEnum] = mapped_column(
        SQLEnum(ProblemTypeEnum, name="problem_type_enum", native_enum=False), nullable=False)  # coding, multiple_choice, short_answer, subjective

    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=lambda: [], nullable=False)
    
    prev_problem_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("problem.problem_id"), nullable=True)  # 이전 문제와의 연결
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, nullable=True)

    
    # 임시 필드들 사용시 주석으로 사용 용도 표시
    temporary_field_int_1: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 임시 필드 1 (정수)
    temporary_field_int_2: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 임시 필드 2 (정수)
    temporary_field_int_3: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 임시 필드 3 (정수)
    temporary_field_int_4: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 임시 필드 4 (정수)
    temporary_field_int_5: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 임시 필드 5 (정수)
    
    temporary_field_str_1: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 임시 필드 1 (문자열)
    temporary_field_str_2: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 임시 필드 2 (문자열)
    temporary_field_str_3: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 임시 필드 3 (문자열)
    temporary_field_str_4: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 임시 필드 4 (문자열)
    temporary_field_str_5: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 임시 필드 5 (문자열)

    temporary_field_datetime_1: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # 임시 필드 1 (날짜/시간)
    temporary_field_datetime_2: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # 임시 필드 2 (날짜/시간)

    temporary_field_json: Mapped[Dict | None] = mapped_column(JSONB, nullable=True)  # 임시 JSON 필드 (구조화 데이터 저장용)

    # 추가 필드 필요 시 연결되는 테이블 링크
    temporary_table_link: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
    __mapper_args__ = {
    "polymorphic_on": problem_type,
    "with_polymorphic": "*"
    }