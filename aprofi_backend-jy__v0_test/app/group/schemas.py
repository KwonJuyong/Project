from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum
from sqlalchemy.ext.asyncio import create_async_engine



# --------------- group ---------------
class GroupCreate(BaseModel):
    group_name: str
    group_private_state: bool

class GroupCopy(BaseModel):
    group_id: int
    group_name: str
    group_private_state: bool
    members: Optional[List[str]] = None
    
class GroupAllGetResponse(BaseModel):
    group_id: int
    group_name: str
    group_owner: str
    group_private_state: bool
    is_member: bool
    is_pending_member: bool    
    member_count: int  # 연산 후 전달

class GroupGetResponse(BaseModel):
    group_id: int
    group_name: str
    group_owner: str
    group_private_state: bool
    member_count: int  # 연산 후 전달
    createdAt: Optional[str] = None  # 생성일자, 선택적 필드
    is_member: bool = False  # 현재 사용자가 그룹의 멤버인지 여부
    is_pending_member: bool = False  # 현재 사용자가 그룹 가입 요청을 보냈는지 여부


class GroupMyGetResponse(BaseModel):
    group_id: int
    group_name: str
    group_owner: str
    group_private_state: bool
    member_count: int  # 연산 후 전달


class GroupShowResponse(BaseModel):
    group_name: str
    group_owner: str
    group_private_state: bool
    member_count: int


class GroupMemberResponse(BaseModel):
    user_id: str
    username: str
    email: EmailStr
    timestamp_requested: datetime
    timestamp_approved: datetime
    


class GroupUpdateRequest(BaseModel):
    group_name: Optional[str] = None
    group_private_state: bool


class GroupDeleteResponse(BaseModel):
    message: str


class GroupMemberKickoffResponse(BaseModel):
    message: str


class MemberRequestResponse(BaseModel):
    message: str

class MemberRequestListResponse(BaseModel):
    user_id: str
    username: str
    timestamp_requested: datetime

class MemberRequestProcessRequest(BaseModel):
    user_id: str
    request_state: bool


class MemberRequestProcessResponse(BaseModel):
    message: str
