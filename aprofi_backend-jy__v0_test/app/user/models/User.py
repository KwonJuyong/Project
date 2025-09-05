from datetime import datetime
import json

from sqlalchemy import Integer, String, DateTime, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from typing import Dict
from app.database import Base
from app.security import pwd_context

class User(Base):
    __tablename__ = "user"  # PostgreSQL 예약어이므로 운영 환경에서는 'users'로 권장

    user_id: Mapped[str] = mapped_column(String, primary_key=True, unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # 새로 추가된 필드들
    age: Mapped[str] = mapped_column(String(100), nullable=False)  # 나이 (정수로 바꾸는 것을 고려할 수 있음)
    # TODO: 성별 필드는 프론트엔드에서 추가할 예정
    gender: Mapped[str] = mapped_column(String(100), nullable=False)
    birthday: Mapped[datetime] = mapped_column(DateTime, nullable=True)  # 생년월일 (현재는 nullable=True로 설정, 필요시 필수로 변경 가능)
    phone: Mapped[str] = mapped_column(String(100), nullable=True)  # 전화번호 (현재는 nullable=True로 설정, 필요시 필수로 변경 가능
    address: Mapped[str] = mapped_column(String(255), nullable=True)  # 주소 (현재는 nullable=True로 설정, 필요시 필수로 변경 가능)
    school: Mapped[str] = mapped_column(String(255), nullable=True)  # 소속 학교 (현재는 nullable=True로 설정, 필요시 필수로 변경 가능)

    user_type: Mapped[str] = mapped_column(ARRAY(String), nullable=False, default='student')  # 사용자 유형 (학생, 교수 등)

    # 교수 관련 필드
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 소속 학과
    position: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 직위 (예: 조교수, 부교수 등)
    office: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 연구실 위치
    expertise: Mapped[str | None] = mapped_column(Text, nullable=True)  # 전공 분야
    introduction: Mapped[str | None] = mapped_column(Text, nullable=True)  # 자기소개 또는 약력

    # 학생 관련 필드
    grade: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 학년 (1학년, 2학년 등)
    major: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 전공
    interests: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)  # 관심사
    learning_goals: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)  # 학습목표
    preferred_fields: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)  # 희망 분야
    programming_experience_level: Mapped[str | None] = mapped_column(String(50), nullable=True)  # 프로그래밍 경험 수준
    preferred_programming_languages: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)  # 선호 프로그래밍 언어

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

    def set_password(self, password: str) -> None:
        self.hashed_password = pwd_context.hash(password)

    def check_password(self, password: str) -> bool:
        return pwd_context.verify(password, self.hashed_password)

    def set_profile_info(self, profile_info: dict) -> None:
        self.profile_info = json.dumps(profile_info, ensure_ascii=False)
        self.profile_completed = True

    def get_profile_info(self) -> dict:
        if self.profile_info:
            return json.loads(self.profile_info)
        return {}
