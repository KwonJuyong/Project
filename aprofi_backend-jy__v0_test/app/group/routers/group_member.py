
from ..crud.group import is_member_of_group, get_current_user_info
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import aliased
from typing import Annotated, List
from ..crud.group_request import delete_group_member
from ..crud.group import get_group_by_group_id, get_user_info, is_group_owner
from app.database import get_db
from ..models.group import Group as GroupModel
from ..models.group_request import GroupUserRequest
from ..models.group_member import GroupUser
from ..schemas import GroupMemberResponse, GroupMemberKickoffResponse
from app.security import get_current_user
from json import dumps

router = APIRouter(
    prefix="/groups"
)

@router.get("/members/{group_id}", response_model=list[GroupMemberResponse])
async def read_group_member_endpoint(
        group_id: int,
        current_user: Annotated[dict, Depends(get_current_user)],
        db: AsyncSession = Depends(get_db)
):
    actual_user_id = await get_current_user_info(db, current_user)
    
    # Check if group exists
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
    
    owner_id = group_data.owner_id
    
    # GroupUser와 GroupUserRequest를 조인해서 멤버, 요청시간 함께 가져오기
    request_alias = aliased(GroupUserRequest)
    result = await db.execute(
        select(GroupUser, request_alias.timestamp)
        .join(
            request_alias,
            (GroupUser.user_id == request_alias.user_id) &
            (GroupUser.group_id == request_alias.group_id),
            isouter=True
        )
        .where(
            GroupUser.group_id == group_id,
            GroupUser.user_id != owner_id,  # ← 그룹장은 제외
            GroupUser.deleted_at.is_(None)
        )
    )

    rows = result.all()

    # 각 멤버별 유저 정보 및 응답 구성
    response_list = []
    for member, requested_timestamp in rows:
        email, username = await get_user_info(db, member.user_id)
        response_list.append(GroupMemberResponse(
            user_id=member.user_id,
            username=username,
            email=email,
            timestamp_requested=requested_timestamp,
            timestamp_approved=member.created_at
        ))

    return response_list

# delete 라우팅 충돌로 경로 수정
@router.delete("/kickoff/{group_id}/{user_id}", response_model=GroupMemberKickoffResponse)
async def delete_group_member_endpoint(
        group_id: int, user_id: str, 
        current_user: Annotated[dict, Depends(get_current_user)],
        db: AsyncSession = Depends(get_db)
):
    actual_user_id = await get_current_user_info(db, current_user)
    
    if not await is_group_owner(db, group_id, actual_user_id):
        raise HTTPException(status_code=403, detail={
            "msg": "그룹원을 추방할 권한이 없습니다."
        })

    # Use the new CRUD function for deleting group members
    success = await delete_group_member(db, group_id, user_id)
    
    if success:
        return GroupMemberKickoffResponse(message="그룹원이 성공적으로 추방되었습니다.")
    else:
        raise HTTPException(
            status_code=404, detail={
                "msg": "해당 사용자를 그룹에서 찾을 수 없습니다."
            }
        )
