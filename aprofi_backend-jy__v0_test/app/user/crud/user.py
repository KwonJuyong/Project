from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, selectinload

from ..schemas import RegisterRequest
from ..models.User import User
from app.security import hash_password, verify_password
from datetime import datetime
import json


async def is_user_exist(db: AsyncSession, user_id: str):  # TODO : 버그 존재
    statement = select(User).where(User.user_id == user_id)
    tmp = await db.execute(statement)
    existing_user = tmp.scalars().first()
    if existing_user:
        raise ValueError(f'This user_id:{user_id} already exists.')
    return True


async def is_email_exist(db: AsyncSession, email: str):
    statement = select(User).where(User.email == email)
    tmp = await db.execute(statement)
    existing_user = tmp.scalars().first()
    if existing_user:
        raise ValueError(f'This email:{email} already exists.')
    return True


# register
async def create_user(db: AsyncSession, request: RegisterRequest):
    await is_user_exist(db, request.user_id)
    hashed_password = hash_password(request.password)
     # 리스트 필드를 쉼표로 join
    profile = request.profile_info
    new_user = User(
        user_id=request.user_id,
        hashed_password=hashed_password,
        username=request.username,
        email=request.email,
        gender=request.gender,
        age=profile.age,
        grade=profile.grade,
        major=profile.major,
        interests=profile.interests,
        learning_goals=profile.learning_goals,
        preferred_fields=profile.preferred_fields,
        programming_experience_level=profile.programming_experience_level,
        preferred_programming_languages=profile.preferred_programming_languages
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return {"message": f"User({request.user_id}) created successfully"}

# login
async def check_user(db: AsyncSession, user_id: str, password: str) -> User:
    statement = select(User).where(User.user_id == user_id)
    result = await db.execute(statement)
    user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.hashed_password):
        raise ValueError("Invalid id or password")

    return user


async def get_user_info(db: AsyncSession, user_id: str):
    result = await db.execute(
        select(User.user_id, User.email, User.username)
        .where(User.user_id == user_id)
    )
    user_info = result.first()
    return user_info


# User 존재하지 않을 시 에러 처리 필요
async def get_user_by_user_id(user_id: str, db: AsyncSession):
    statement = select(User).where(User.user_id == user_id)
    result = await db.execute(statement)
    return result.scalar_one_or_none()