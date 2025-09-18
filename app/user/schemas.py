from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum
from sqlalchemy.ext.asyncio import create_async_engine



# --------------- user ---------------
class User(BaseModel):
    user_uuid: int
    user_id: str
    hashed_password: str
    username: str
    email: EmailStr


class ProfileInfo(BaseModel):
    age: str
    grade: str
    major: str
    interests: List[str]
    learning_goals: List[str]
    preferred_fields: List[str]
    programming_experience_level: str
    preferred_programming_languages: List[str]

class RegisterRequest(BaseModel):
    user_id: str
    password: str
    username: str
    email: EmailStr
    gender: str
    profile_info: ProfileInfo


class LoginRequest(BaseModel):
    user_id: str
    password: str


class TokenData(BaseModel):
    access_token: str
    token_type: str


# FastAPI는 Pydantic 모델을 통해 응답 데이터를 검증 및 직렬화하기 때문에 Pydantic 스키마를 만들어야 합니다.
class UserResponse(BaseModel):
    user_id: str
    username: str
    email: EmailStr


class ChangePasswordRequest(BaseModel):
    user_id: str
    current_password: str
    new_password: str
    
class CheckResponse(BaseModel):
    available: bool
    message: str
