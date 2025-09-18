from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated, List

from ..crud.group_request import create_member_request, get_member_requests_for_group, process_member_request
from ..crud.group import is_group_owner, get_current_user_info
from app.database import get_db
from ..schemas import MemberRequestResponse, MemberRequestListResponse, MemberRequestProcessRequest, MemberRequestProcessResponse
from app.security import get_current_user

router = APIRouter(
    prefix="/member_request"
)


@router.post("/{group_id}", response_model=MemberRequestResponse)
async def create_member_request_endpoint(
    group_id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    """그룹 가입 요청"""
    actual_user_id = await get_current_user_info(db, current_user)
    
    await create_member_request(db, group_id, actual_user_id)
    return MemberRequestResponse(
        message="그룹 가입 요청이 성공적으로 전송되었습니다."
    )


@router.get("/my-group", response_model=List[MemberRequestListResponse])
async def get_member_requests_endpoint(
    group_id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    """그룹 가입 요청 목록 조회 (그룹장용)"""
    actual_user_id = await get_current_user_info(db, current_user)
    
    # Check if user is group owner
    if not await is_group_owner(db, group_id, actual_user_id):
        raise HTTPException(status_code=403, detail="그룹장이 아닙니다.")
    
    requests = await get_member_requests_for_group(db, group_id)
    
    return [
        MemberRequestListResponse(
            user_id=req[0].user_id,
            username=req[1].username,
            timestamp_requested=req[0].timestamp  # 각 요청의 timestamp
        )
        for req in requests
    ]



@router.patch("/group-invites/{group_id}", response_model=MemberRequestProcessResponse)
async def process_member_request_endpoint(
    group_id: int,
    request_data: MemberRequestProcessRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    """그룹 가입 요청 처리"""
    actual_user_id = await get_current_user_info(db, current_user)
    
    try:
        await process_member_request(db, group_id, request_data.user_id, request_data.request_state, actual_user_id)
        action = "수락" if request_data.request_state else "거절"
        return MemberRequestProcessResponse(
            message=f"가입 요청이 성공적으로 {action}되었습니다."
        )
    except HTTPException as e:
        raise e
