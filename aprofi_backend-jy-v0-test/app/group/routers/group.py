from ..crud.group import delete_group, is_member_of_group, count_group_members, get_current_user_info
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Annotated, List
from ..crud.group import create_group, get_all_groups, get_user_groups, get_group_by_group_id, is_group_owner, soft_update_group
from app.database import get_db
from ..models.group import Group as GroupModel
from ..models import group_member
from ..schemas import GroupCreate, GroupAllGetResponse, GroupMyGetResponse, GroupShowResponse, GroupUpdateRequest, GroupDeleteResponse
from app.security import get_current_user
from json import dumps

router = APIRouter(
    prefix="/groups"
)


@router.post("")
async def create_group_endpoint(
        group: GroupCreate,
        current_user: Annotated[dict, Depends(get_current_user)],  # 로그인한 사용자 정보
        db: AsyncSession = Depends(get_db)
):
 
    # Get actual user_id from database
    actual_user_id = await get_current_user_info(db, current_user)
    
    orm_group = GroupModel(
        group_name=group.group_name,
        is_public=group.group_private_state,
        owner_id=actual_user_id,
    )
    created_group = await create_group(db, orm_group)
    
    # Add creator as member
    group_members = group_member.GroupUser(
        user_id=actual_user_id,
        group_id=created_group.group_id
    )
    db.add_all([group_members])
    await db.commit()
    
    return JSONResponse(
        status_code=200,
        content={
            "msg": "잘 생성된거 같아요"
        }
    )


@router.get("", response_model=List[GroupAllGetResponse])
async def read_all_groups_endpoint(
        current_user: Annotated[dict, Depends(get_current_user)],
        db: AsyncSession = Depends(get_db)
):
    actual_user_id = await get_current_user_info(db, current_user)
    return await get_all_groups(db, actual_user_id)


@router.get("/my", response_model=List[GroupMyGetResponse])
async def read_my_groups_endpoint(
        current_user: Annotated[dict, Depends(get_current_user)],
        db: AsyncSession = Depends(get_db)
):
    actual_user_id = await get_current_user_info(db, current_user)
    return await get_user_groups(db, actual_user_id)


@router.get("/{group_id}", response_model=GroupShowResponse)
async def read_group_to_show_endpoint(
        group_id: int,
        current_user: Annotated[dict, Depends(get_current_user)],
        db: AsyncSession = Depends(get_db)
):
    actual_user_id = await get_current_user_info(db, current_user)
    
    group_data = await get_group_by_group_id(db, group_id)
    if group_data is None:
        raise HTTPException(status_code=404, detail={
            "msg": "그룹을 찾을 수 없습니다."
        })
    
    # Check if user is member
    is_member = await is_member_of_group(db, group_id, actual_user_id)
    if not is_member:
        raise HTTPException(status_code=403, detail={
            "msg": "그룹 멤버가 아닙니다."
        })

    member_count = await count_group_members(db, group_id)
    
    return GroupShowResponse(
        group_name=group_data.group_name,
        group_owner=group_data.owner_id,
        group_private_state=group_data.is_public,
        member_count=member_count
    )


@router.put("/{group_id}")
async def update_group_endpoint(
    group_id: int,
    group_update: GroupUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    actual_user_id = await get_current_user_info(db, current_user)
    
    # Check if group exists
    group_data = await get_group_by_group_id(db, group_id)
    if not group_data:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다.")
    
    # Check if user is group owner
    if not await is_group_owner(db, group_id, actual_user_id):
        raise HTTPException(status_code=403, detail="그룹을 수정할 권한이 없습니다.")

    # Update group using CRUD function
    update_data = {
    "group_name": group_update.group_name,
    "is_public": group_update.group_private_state  # 조건 없이 무조건 대입!
    }
    updated_group = await soft_update_group(db, group_id, **update_data)
    
    if not updated_group:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다.")
    
    return

# 그룹 삭제 엔드포인트
@router.delete("/{group_id}", response_model=GroupDeleteResponse)
async def delete_group_endpoint(
        group_id : int,
        current_user: Annotated[dict, Depends(get_current_user)],
        db: AsyncSession = Depends(get_db)
):
    actual_user_id = await get_current_user_info(db, current_user)
    
    if not await is_group_owner(db, group_id, actual_user_id):
        raise HTTPException(status_code=403, detail={
            "msg": "그룹을 삭제할 권한이 없습니다."
        })

    result = await delete_group(db, group_id)
    return GroupDeleteResponse(message="그룹이 성공적으로 삭제되었습니다.")

