from datetime import datetime
from typing import Dict, Any

from sqlalchemy import Integer, String, DateTime, Boolean, ForeignKey, text
from sqlalchemy.orm import Mapped, mapped_column  # relationship 추가
from sqlalchemy.dialects.postgresql import JSONB

from sqlalchemy.sql import func

from app.database import Base

class Workbook(Base):
    __tablename__ = "workbook"

    workbook_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workbook_name: Mapped[str] = mapped_column(String, nullable=False)
    
    # 주의: group은 SQL 예약어이므로 실제 DB에서 충돌 가능. 테이블명을 group → user_group 등으로 변경 고려
    group_id: Mapped[int] = mapped_column(ForeignKey("group.group_id"), nullable=False)

    description: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('false'), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 시험 관련 필드들
    is_test_mode: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('false'), nullable=False)
    test_start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    test_end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 게시 기간 관련 필드들
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # 괄호 수정됨

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

    temporary_field_json: Mapped[Dict[str, Any] | None] = mapped_column(JSONB, nullable=True)  # 임시 JSON 필드 (구조화 데이터 저장용)

    # 추가 필드 필요 시 연결되는 테이블 링크
    temporary_table_link: Mapped[int | None] = mapped_column(ForeignKey("workbook.workbook_id", ondelete="SET NULL"), nullable=True)
