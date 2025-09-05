from datetime import datetime
from sqlalchemy import Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.database import Base
from typing import Dict, List
from sqlalchemy.dialects.postgresql import JSONB


class Group(Base):
    __tablename__ = "group"

    group_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_name: Mapped[str] = mapped_column(String(100), nullable=False)
    
    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    owner_id: Mapped[str] = mapped_column(String(50), ForeignKey("user.user_id"), nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, default= None, nullable=True)
    

    # 임시 필드들 사용시 주석으로 사용 용도 표시
    temporary_field_int_1: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 임시 필드 1 (정수)
    temporary_field_int_2: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 임시 필드 2 (정수)
   
    temporary_field_str_1: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 임시 필드 1 (문자열)
    temporary_field_str_2: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 임시 필드 2 (문자열)
    
    temporary_field_datetime_1: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # 임시 필드 1 (날짜/시간)
    temporary_field_datetime_2: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # 임시 필드 2 (날짜/시간)

    temporary_field_json: Mapped[Dict | None] = mapped_column(JSONB, nullable=True)  # 임시 JSON 필드 (구조화 데이터 저장용)
    
    temporary_table_link: Mapped[str | None] = mapped_column(String(100), nullable=True)