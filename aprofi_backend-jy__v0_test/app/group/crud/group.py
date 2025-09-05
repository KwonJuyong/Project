from fastapi import HTTPException
from fastapi.responses import JSONResponse

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.sql import func, case, exists
from sqlalchemy import update

from ..schemas import GroupAllGetResponse, GroupGetResponse, GroupMyGetResponse, GroupShowResponse, GroupMemberResponse
from ..models import group, group_member, group_request 
from ..models.group_request import RequestState
from app.user.models import User
from datetime import datetime

#   !!중요!!
#   정말 죄송합니다.
#   아래 코드를 보시면 group.Group.~~~ // 선언 방식: 파일명.클래스명.필드명
#   이런식으로 코드가 작성되어 있습니다. 이건 첫번째로 오는게 models의 파일명입니다.
#   두번째로 오는건 파일명 뒤에 있는 클래스명입니다.
#   즉, group.Group는 group.py 파일에 있는 Group 클래스입니다.
#   이걸로 인해 코드가 길어지는 점 양해 부탁드립니다.
#   죄송합니다. 다음부터는 이렇게 작성하지 않겠습니다.
#   ㅎㅎ

async def create_group(db: AsyncSession, group_data: group.Group) -> group.Group:
    db.add(group_data)
    await db.commit()
    await db.refresh(group_data)
    return group_data

async def get_group_by_group_id(db: AsyncSession, group_id: int):
    result = await db.execute(select(group.Group)
        .where(
            (group.Group.group_id == group_id) &
            (group.Group.deleted_at.is_(None))
        )
    )
    return result.scalar_one_or_none()


async def is_group_owner(db: AsyncSession, group_id: int, user_id: str):
    result = await db.execute(
        select(group.Group.owner_id)
        .where(
            (group.Group.group_id == group_id) &
            (group.Group.owner_id == user_id) &
            (group.Group.deleted_at.is_(None))
        )
    )
    owner = result.scalar_one_or_none()
    print(f"[디버깅] group_id={group_id}, user_id={user_id}, owner_in_db={owner}")
    return owner == user_id

async def get_user_groups(db: AsyncSession, user_id: str):
    member_count_subquery = (
        select(group_member.GroupUser.group_id, func.count(group_member.GroupUser.user_id).label("member_count"))
        .where(group_member.GroupUser.deleted_at.is_(None))
        .group_by(group_member.GroupUser.group_id)
        .subquery()
    )

    # 그룹 데이터만 가져오도록 최적화
    query = (
        select(
            group.Group.group_id,
            group.Group.group_name,
            group.Group.owner_id,
            group.Group.is_public,
            func.coalesce(member_count_subquery.c.member_count, 0).label("member_count")  # 멤버 수 추가
        )
        .outerjoin(member_count_subquery, group.Group.group_id == member_count_subquery.c.group_id)
        .where(
            ((group.Group.owner_id == user_id) |  # 유저가 소유한 그룹
            (group.Group.group_id.in_(  # 유저가 속한 그룹
                select(group_member.GroupUser.group_id).where(
                    (group_member.GroupUser.user_id == user_id) &
                    (group_member.GroupUser.deleted_at.is_(None))
                )
            )))
            & (group.Group.is_deleted == False)
        )
    )

    result = await db.execute(query)
    groups = result.all()  # 필요한 필드만 반환
    return [GroupMyGetResponse(
        group_id=row.group_id,
        group_name=row.group_name,
        group_owner=row.owner_id,
        group_private_state=row.group_private_state,
        member_count=row.member_count,
    ) for row in groups]


async def get_user_groups(db: AsyncSession, user_id: str):
    member_count_subquery = (
        select(group_member.GroupUser.group_id, func.count(group_member.GroupUser.user_id).label("member_count"))
        .where(group_member.GroupUser.deleted_at.is_(None))
        .group_by(group_member.GroupUser.group_id)
        .subquery()
    )

    # 그룹 데이터만 가져오도록 최적화
    query = (
        select(
            group.Group.group_id,
            group.Group.group_name,
            group.Group.owner_id,
            group.Group.is_public,
            func.coalesce(member_count_subquery.c.member_count, 0).label("member_count")  # 멤버 수 추가
        )
        .outerjoin(member_count_subquery, group.Group.group_id == member_count_subquery.c.group_id)
        .where(
            ((group.Group.owner_id == user_id) |  # 유저가 소유한 그룹
            (group.Group.group_id.in_(  # 유저가 속한 그룹
                select(group_member.GroupUser.group_id).where(
                    (group_member.GroupUser.user_id == user_id) &
                    (group_member.GroupUser.deleted_at.is_(None))
                )
            )))
            & (group.Group.deleted_at.is_(None))
        )
    )

    result = await db.execute(query)
    groups = result.all()  # 필요한 필드만 반환
    return [GroupMyGetResponse(
        group_id=row.group_id,
        group_name=row.group_name,
        group_owner=row.owner_id,
        group_private_state=row.is_public,
        member_count=row.member_count,
    ) for row in groups]


async def get_all_groups(db: AsyncSession, user_id: str):
    result = await db.execute(
        select(group.Group)
        .where(
            (group.Group.deleted_at.is_(None))  # 삭제되지 않은 그룹만
            & (group.Group.is_public.is_(False))  # 공개 그룹만
            & exists(
                select(group_member.GroupUser)
                .where(
                    (group_member.GroupUser.group_id == group.Group.group_id) &
                    (group_member.GroupUser.deleted_at.is_(None))  # 현재 사용자가 그룹의 멤버인 경우
                )
            )
        )
    )
    
    groups = result.scalars().all()
    
    # 각 그룹에 대해 현재 사용자의 멤버십 상태 확인
    group_responses = []
    for kk in groups:
        # 현재 사용자가 그룹의 멤버인지 확인
        is_member = await is_member_of_group(db, kk.group_id, user_id)
        
        # 현재 사용자가 가입 요청을 보냈는지 확인
        is_pending_member_response = await is_pending_member(db, kk.group_id, user_id)
        
        # 멤버 수 계산
        member_count = await count_group_members(db, kk.group_id)
        
        group_responses.append(GroupAllGetResponse(
            group_id=kk.group_id,
            group_name=kk.group_name,
            group_owner=kk.owner_id,
            group_private_state=kk.is_public,
            member_count=member_count,
            is_member=is_member,
            is_pending_member=is_pending_member_response
        ))
    
    return group_responses

async def is_member_of_group(db: AsyncSession, group_id: int, user_id: str):
    result = await db.execute(
        select(group_member.GroupUser)
        .where(
            (group_member.GroupUser.group_id == group_id) &
            (group_member.GroupUser.user_id == user_id) &
            (group_member.GroupUser.deleted_at.is_(None))
        )
    )
    return result.scalar_one_or_none() is not None

async def is_pending_member(db: AsyncSession, group_id: int, user_id: str):
    result = await db.execute(
        select(group_request.GroupUserRequest)
        .where(
            (group_request.GroupUserRequest.group_id == group_id) &
            (group_request.GroupUserRequest.user_id == user_id) &
            (group_request.GroupUserRequest.request_state == RequestState.PENDING)
        )
    )
    return result.scalar_one_or_none() is not None

async def get_group_members(db: AsyncSession, group_id: int):
    result = await db.execute(
        select(group_member.GroupUser)
        .where(
            (group_member.GroupUser.group_id == group_id) &
            (group_member.GroupUser.deleted_at.is_(None))
        )
    )
    return result.scalars().all()


async def count_group_members(db: AsyncSession, group_id: int):
    result = await db.execute(
        select(func.count(group_member.GroupUser.group_id))
        .where(
            (group_member.GroupUser.group_id == group_id) &
            (group_member.GroupUser.deleted_at.is_(None))
        )
    )
    return result.scalar_one_or_none() or 0


async def delete_group(db: AsyncSession, group_id: int):
    result = await db.execute(
        select(group.Group).where(
            (group.Group.group_id == group_id) &
            (group.Group.is_deleted == False)
        )
    )
    group_instance = result.scalar_one_or_none()

    if not group_instance:
        raise HTTPException(
            status_code=404,
            detail={
                "msg": f"group_id가 {group_id}인 그룹이 존재하지 않아요..."
            })

    await db.execute(
        update(group.Group)
        .where(group.Group.group_id == group_id)
        .values(is_deleted=True, deleted_at=func.now())
    )

    await db.commit()
    return JSONResponse(
        status_code=200,
        content={
            "msg": f"그룹({group_id})이 정상적으로 삭제 되었습니다..."
        }
    )


#이 함수는 기존 그룹의 정보를 바꾸는게 아니라 기존 그룹을 삭제 처리만 하고
#수정된 내용을 기반으로 새로운 그룹을 생성하는 함수입니다.
async def soft_update_group(db: AsyncSession, group_id: int, **update_data):
    result = await db.execute(
        select(group.Group).where(
            (group.Group.group_id == group_id) &
            (group.Group.deleted_at.is_(None))
        )
    )
    group_instance = result.scalar_one_or_none()
    now = datetime.now()

    if not group_instance:
        return None

    # 2. 기존 그룹 soft delete 처리
    group_instance.is_deleted = True
    group_instance.deleted_at = now
    await db.flush()  # 아직 commit은 하지 않음

    # 3. 새 그룹 생성 (복사 + 업데이트 적용)
    new_group = group.Group(
        group_name=update_data.get("group_name", group_instance.group_name),
        is_public=update_data.get("is_public", group_instance.is_public),
        owner_id=group_instance.owner_id
    )

    db.add(new_group)
    await db.flush()
    
    result = await db.execute(
        select(group_member.GroupUser).where(
            (group_member.GroupUser.group_id == group_id) &
            (group_member.GroupUser.is_deleted.is_(False))
        )
    )
    group_users = result.scalars().all()

    # 5. 기존 GroupUser -> soft delete + 새 그룹에 복사
    for old_member in group_users:
        # 기존 레코드 soft delete
        old_member.is_deleted = True
        old_member.deleted_at = now

        # 새 그룹에 동일한 유저 생성 (created_at 복사)
        new_member = group_member.GroupUser(
            group_id=new_group.group_id,
            user_id=old_member.user_id,
            created_at=old_member.created_at
        )
        db.add(new_member)
        
    result = await db.execute(
        select(group_request.GroupUserRequest).where(
            group_request.GroupUserRequest.group_id == group_id
        )
    )
    group_requests = result.scalars().all()

    for request in group_requests:
        new_request = group_request.GroupUserRequest(
            user_id=request.user_id,
            group_id=new_group.group_id,
            request_state=request.request_state,
            timestamp=request.timestamp
        )
        db.add(new_request)
    await db.commit()
    await db.refresh(new_group)
    return new_group



async def get_user_info(db: AsyncSession, user_id: str):
    """Get user information for group member responses"""
    result = await db.execute(
        select(User.User.email, User.User.username)
        .where(User.User.user_id == user_id)
    )
    user_info = result.first()
    if user_info:
        return user_info.email, user_info.username
    return None, None


async def get_current_user_info(db: AsyncSession, current_user: dict):
    """Get current user information from JWT token"""
    # JWT 토큰에서 user_id를 가져옴
    user_id = current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user token")
    
    print(f"DEBUG: JWT token user_id: {user_id}")
    print(f"DEBUG: Current user dict: {current_user}")
    
    # 데이터베이스에서 사용자 정보 확인
    result = await db.execute(
        select(User.User.user_id, User.User.username, User.User.email)
        .where(User.User.user_id == user_id)
    )
    user = result.first()
    print(f"DEBUG: Found user: {user.user_id}")
    return user.user_id




