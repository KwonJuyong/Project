from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.sql import func
from sqlalchemy import update
from ..models.group_member import GroupUser 
# 상대 경로가 아닌, 절대 경로로 지정. 아니면 엿됨


async def get_group_members(db: AsyncSession, group_id: int):
    result = await db.execute(
        select(GroupUser)
        .where(
            (GroupUser.group_id == group_id) &
            (GroupUser.deleted_at.is_(None))
            )
        )
    return result.scalars().all()

#추방
async def delete_group_member(db: AsyncSession, group_id: int, user_id: str):
    result = await db.execute(
        select(GroupUser)
        .where(
            (GroupUser.group_id == group_id)&
            (GroupUser.user_id == user_id)
            )
        )

    group_member = result.scalar_one_or_none()
    if not group_member:
        raise HTTPException(
            status_code = 404, 
            detail={
                "msg":f"그룹 {group_id}에 사용자 {user_id}가 존재하지 않아요."
                })

    await db.execute(
        update(GroupUser)
        .where(
            (GroupUser.group_id == group_id)&
            (GroupUser.user_id == user_id)
        )
        .values(deleted_at = func.now())
    )

    await db.commit()
    return JSONResponse(
        status_code=200,
        detail={
            "msg":f"그룹 {group_id}에 사용자 {user_id}를 추방했습니다."
        }
    )

