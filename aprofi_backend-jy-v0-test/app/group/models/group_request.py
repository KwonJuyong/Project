
from datetime import datetime
from sqlalchemy import Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.types import Enum as SQLEnum
from enum import Enum

from app.database import Base

class RequestState(str, Enum):
        PENDING = "PENDING"
        ACCEPTED = "ACCEPTED"
        REJECTED = "REJECTED"

class GroupUserRequest(Base):
    """그룹 유저 요청 모델.
    그룹과 User 간의 요청 관계를 관리하는 모델입니다.
    이 모델은 요청 상태를 관리하며, 요청이 PENDING 상태일 때만 유효합니다.
    요청 상태는 ACCEPTED, PENDING, REJECTED 중 하나입니다.  
    요청이 생성되면 기본적으로 PENDING 상태로 설정됩니다.
    """
    
    __tablename__ = "group_user_request"

    group_member_request_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("user.user_id"), nullable=False)
    group_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("group.group_id"), nullable=False)

    # 요청 상태: RequestState(PENDING, ACCEPTED, REJECTED)
    # 기본값은 PENDING으로 설정
    request_state: Mapped[RequestState] = mapped_column(SQLEnum(RequestState), default=RequestState.PENDING, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)


    