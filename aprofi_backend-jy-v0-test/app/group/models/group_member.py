from datetime import datetime
from sqlalchemy import Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.types import Enum as SQLEnum
from typing import Dict
from sqlalchemy.dialects.postgresql import JSONB

from app.database import Base

class GroupUser(Base):
    """그룹 안 사용자 관리 모델
    이 모델은 그룹 내 사용자의 역할과 접근 권한을 관리합니다.
    각 사용자는 그룹 내에서 특정 역할을 가지며, 해당 역할에 따라 접근 권한이 달라집니다.
    예를 들어, 사용자는 "member" 또는 "admin" 역할을 가질 수 있으며,
    각 역할에 따라 "read", "write", "manage" 등의 접근 권한을 가집니다.
    이 모델은 그룹과 사용자 간의 관계를 정의하며, 그룹 내에서 사용자의 역할과 접근 권한을 관리합니다.
    """
    
    __tablename__ = "group_user"

    group_id: Mapped[int] = mapped_column(ForeignKey("group.group_id"), nullable=False, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("user.user_id"), nullable=False, primary_key=True)
    
    # 언제 그룹에 추가되었는지 기록
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    
    # 그룹에 제거된 시간 기록
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, nullable=True)
    
    temporary_field_int_1: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 임시 필드 1 (정수)
    temporary_field_int_2: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 임시 필드 2 (정수)
   
    temporary_field_str_1: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 임시 필드 1 (문자열)
    temporary_field_str_2: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 임시 필드 2 (문자열)
    
    temporary_field_datetime_1: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # 임시 필드 1 (날짜/시간)
    temporary_field_datetime_2: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # 임시 필드 2 (날짜/시간)

    temporary_field_json: Mapped[Dict | None] = mapped_column(JSONB, nullable=True)  # 임시 JSON 필드 (구조화 데이터 저장용)
    
    temporary_table_link: Mapped[str | None] = mapped_column(String(100), nullable=True)
    
