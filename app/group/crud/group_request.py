from fastapi import HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import and_
from sqlalchemy import update
from ..crud.group import get_group_by_group_id, is_member_of_group,is_group_owner
from ..models.group_request import GroupUserRequest, RequestState
from ..models.group import Group
from ..models.group_member import GroupUser
from app.user.models.User import User
from datetime import datetime

async def create_member_request(db: AsyncSession, group_id: int, user_id: str):
    """Create a group membership request"""
    # Check if group exists
    group = await get_group_by_group_id(db, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다.")
    
    # Check if user is already a member
    if await is_member_of_group(db, group_id, user_id):
        raise HTTPException(status_code=400, detail="이미 그룹 멤버입니다.")
    
    # Check if user already has a pending request
    if await has_active_request(db, group_id, user_id):
        raise HTTPException(status_code=400, detail="이미 가입 요청 중입니다.")
    
    # Create request
    request = GroupUserRequest(
        user_id=user_id,
        group_id=group_id,
        request_state=RequestState.PENDING  # pending
    )
    
    db.add(request)
    await db.commit()
    await db.refresh(request)
    
    return request

async def existing_group_member(user_id: str, group: Group) -> bool:
    return any(member.user_id == user_id for member in group.members)


async def pending_group_req(user_id: str, group: Group) -> bool:
    return any(
        request.user_id == user_id and request.request_state is None
        for request in GroupUserRequest.group_member_request_id
    )

async def read_my_group_invitation_request(db: AsyncSession, group_id: int):
    result = await db.execute(
        select(GroupUserRequest)
        .options(joinedload(GroupUserRequest.user_id))
        .where(and_(
            GroupUserRequest.group_id == group_id,
            GroupUserRequest.request_state.is_(None)
                    )
        )
    )
    return result.scalars().all()


async def update_group_member_request(db: AsyncSession, request_state: bool, user_id: str, group_id: int):
    result = await db.execute(select(GroupUserRequest)
                              .where(and_(GroupUserRequest.request_state.is_(None),
                                          GroupUserRequest.group_id == group_id,
                                          GroupUserRequest.user_id == user_id
                                          )
                                     )
                              )
    problem = result.scalars().first()
    problem.request_state = request_state
    await db.commit()


async def has_active_request(db: AsyncSession, group_id: int, user_id: str) -> bool:
    result = await db.execute(
        select(GroupUserRequest)
        .where(
            GroupUserRequest.group_id == group_id,
            GroupUserRequest.user_id == user_id,
            GroupUserRequest.request_state.in_([
                RequestState.PENDING,
                RequestState.ACCEPTED
            ])
        )
    )
    return result.scalar_one_or_none() is not None

async def get_member_requests_for_group(db: AsyncSession, group_id: int):
    """Get all pending member requests for a group"""
    result = await db.execute(
        select(GroupUserRequest, User)
        .join(User, GroupUserRequest.user_id == User.user_id)
        .where(
            (GroupUserRequest.group_id == group_id) &
            (GroupUserRequest.request_state == RequestState.PENDING)  # pending requests only
        )
    )
    return result.all()

async def process_member_request(db: AsyncSession, group_id: int, requesting_user_id: str, request_state: bool, owner_user_id: str):
    """Process a member request (accept or reject)"""
    # Check if user is group owner
    if not await is_group_owner(db, group_id, owner_user_id):
        raise HTTPException(status_code=403, detail="그룹장이 아닙니다.")
    
    # Find the request
    result = await db.execute(
        select(GroupUserRequest)
        .where(
            (GroupUserRequest.group_id == group_id) &
            (GroupUserRequest.user_id == requesting_user_id) &
            (GroupUserRequest.request_state == RequestState.PENDING)
        )
    )
    request = result.scalar_one_or_none()
    
    if not request:
        raise HTTPException(status_code=404, detail="가입 요청을 찾을 수 없습니다.")
    
    # Update request state
    new_state = RequestState.ACCEPTED if request_state else RequestState.REJECTED
    request.request_state = new_state

    # 수락 시 멤버로 추가
    if request_state:  # True일 때만
        db.add(GroupUser(
            user_id=requesting_user_id,
            group_id=group_id
        ))

    await db.commit()
    return request


async def delete_group_member(db: AsyncSession, group_id: int, user_id: str):
    """Delete a member from a group"""
    result = await db.execute(
        select(GroupUser)
        .where(
            (GroupUser.group_id == group_id) &
            (GroupUser.user_id == user_id) &
            (GroupUser.deleted_at.is_(None))
        )
    )
    member = result.scalar_one_or_none()
    
    if not member:
        return False
    
    # Soft delete the member
    await db.execute(
        update(GroupUser)
        .where(
            (GroupUser.group_id == group_id) &
            (GroupUser.user_id == user_id)
        )
        .values(deleted_at=datetime.now(), is_deleted=True)
    )
    
    await db.commit()
    return True