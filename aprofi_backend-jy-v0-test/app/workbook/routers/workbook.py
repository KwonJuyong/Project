from ..crud.workbook import delete_workbook
from app.group.crud.group import is_group_owner, get_group_members
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated
from app.database import get_db
from app.user.models.User import User
from ..models.workbook import Workbook
from app.group.models.group import Group
from ..schemas import WorkbookCreateRequest,WorkbookCreateResponse, WorkbookGetResponse,  WorkbookUpdateRequest
from ..crud.workbook import create_workbook, get_workbook_by_workbook_id, update_workbook, count_problems_in_workbook, sum_workbook_points
from app.security import get_current_user
from sqlalchemy.future import select
from datetime import datetime

router = APIRouter(prefix="/workbook")

@router.post("", response_model=WorkbookCreateResponse)
async def create_workbook_endpoint(
    workbook: WorkbookCreateRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.user_id == current_user["sub"]))
    user = result.scalars().first()

    if user is None:
        raise HTTPException(status_code=401, detail="Invalid user")

    if workbook.is_test_mode:
        if workbook.test_start_time is None or workbook.test_end_time is None:
            raise HTTPException(status_code=400, detail="시간 등록해라")
    _target_group_owner_coroutine = await db.execute(
        select(Group.owner_id)
        .where(Group.group_id == workbook.group_id)
    )
    target_group_owner = _target_group_owner_coroutine.scalar_one_or_none()
    
    if target_group_owner is None:
        raise HTTPException(status_code=400, detail="그룹 없음요")
    if target_group_owner != current_user["sub"]:
        raise HTTPException(status_code=400, detail=f"그룹장 아님ㅋ target:{target_group_owner}, cur: {current_user['sub']}")

    orm_workbook = Workbook(**workbook.model_dump(exclude={"publication_start_time", "publication_end_time"}))
    orm_workbook.start_date = workbook.publication_start_time
    orm_workbook.end_date = workbook.publication_end_time
    created_workbook = await create_workbook(db, orm_workbook)
    return {
        "msg": f"workbook: {created_workbook.workbook_name} created successfully",
        "workbook_id": created_workbook.workbook_id
    }

@router.get("/group_id/{group_id}", response_model=list[WorkbookGetResponse])
async def read_workbook_by_group_endpoint(
        group_id: int,
        current_user: Annotated[dict, Depends(get_current_user)],
        db: AsyncSession = Depends(get_db)
):
    # TODO 그룹 타인이 참가 만든 후 추가 검증
    if current_user["sub"] not in [group_member.user_id for group_member in await get_group_members(db, group_id)]:
        raise HTTPException(status_code=400, detail="엄 너 이 그룹의 멤버 아닌뎁쇼?")
    
    is_owner = await is_group_owner(db, group_id, current_user["sub"])
    
    condition = [Workbook.group_id == group_id, Workbook.is_deleted == False]
    
    workbook_data = await db.execute(
        select(Workbook)
        .where(*condition)
    )
    workbook_data_result = workbook_data.scalars().all()
    # 각 workbook_id 추출
    workbook_ids = [w.workbook_id for w in workbook_data_result]

    # 문제 수와 총 점수 병렬로 가져오기
    problem_cnt_list = await asyncio.gather(*[
        count_problems_in_workbook(db, wid) for wid in workbook_ids
    ])
    total_points_list = await asyncio.gather(*[
        sum_workbook_points(db, wid) for wid in workbook_ids
    ])

    # 4. 최종 응답 구성
    result = [
        WorkbookGetResponse(
            workbook_id=data.workbook_id,
            group_id=data.group_id,
            workbook_name=data.workbook_name,
            problem_cnt=problem_cnt_list[i],
            creation_date=data.created_at,
            description=data.description,
            is_test_mode=data.is_test_mode,
            test_start_time=data.test_start_time,
            test_end_time=data.test_end_time,
            publication_start_time=data.start_date,
            publication_end_time=data.end_date,
            workbook_total_points=total_points_list[i]
        )
        for i, data in enumerate(workbook_data_result)
    ]

    return result



@router.get("/{workbook_id}", response_model=WorkbookGetResponse)
async def read_workbook_by_workbook_id(
    workbook_id: int,
    db: AsyncSession = Depends(get_db)
):
    workbook_data = await get_workbook_by_workbook_id(db, workbook_id)
    problem_cnt = await count_problems_in_workbook(db, workbook_id)
    workbook_total_points = await sum_workbook_points(db, workbook_id)

    return WorkbookGetResponse(
        workbook_id=workbook_data.workbook_id,
        group_id=workbook_data.group_id,
        workbook_name=workbook_data.workbook_name,
        problem_cnt=problem_cnt,
        creation_date=workbook_data.created_at,
        description=workbook_data.description,
        is_test_mode=workbook_data.is_test_mode,
        test_start_time=workbook_data.test_start_time,
        test_end_time=workbook_data.test_end_time,
        publication_start_time=workbook_data.start_date,
        publication_end_time=workbook_data.end_date,
        workbook_total_points=workbook_total_points
    )


@router.put("/{workbook_id}")
async def update_workbook_data(
        workbook_id: int,
        update_data: WorkbookUpdateRequest,
        current_user: Annotated[dict, Depends(get_current_user)],
        db: AsyncSession = Depends(get_db)
):
    cur_workbook: Workbook = await get_workbook_by_workbook_id(db, workbook_id)
    if not await is_group_owner(db, cur_workbook.group_id, current_user["sub"]):
        raise HTTPException(status_code=403, detail="당신은 해당 그룹의 workbook을 수정할 권리가 없습니다.")

    await update_workbook(db, cur_workbook, update_data)
    return JSONResponse(status_code=200, content={
        "msg": f"workbook_id: {workbook_id} 업데이트 완료"
    })

  
@router.delete("/{group_id}/{workbook_id}")
async def delete_workbook_endpoint(
        group_id: int,
        workbook_id: int,
        current_user: Annotated[dict, Depends(get_current_user)],
        db: AsyncSession = Depends(get_db)
):
    if not await is_group_owner(db, group_id, current_user["sub"]):
        raise HTTPException(status_code=403, detail={
            "msg": f"그룹장 아니십니댜... 뭘 하고 싶으신거죠?"
        })

    return await delete_workbook(db, workbook_id)