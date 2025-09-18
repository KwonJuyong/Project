from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.user.models.User import User

# 아이디 중복 확인
async def is_user_exist(db: AsyncSession, user_id: str):
    statement = select(User).where(User.user_id == user_id)
    tmp = await db.execute(statement)
    existing_user = tmp.scalars().first()
    if existing_user:
        raise ValueError(f"This user_id:{user_id} already exists.")
    return True

# 이메일 중복 확인
async def is_email_exist(db: AsyncSession, email: str):
    statement = select(User).where(User.email == email)
    tmp = await db.execute(statement)
    existing_user = tmp.scalars().first()
    if existing_user:
        raise ValueError(f"This email:{email} already exists.")
    return True
