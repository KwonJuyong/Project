from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func, and_
from typing import Annotated
from ..crud.problem_ref import ( 
    bulk_create_problem_refs, 
    delete_problem_ref_by_ids, 
    get_problem_ref_by_ids,
    read_problem_ref_crud,
    )
from datetime import datetime
from app.group.crud.group import is_group_owner
from app.problem.crud.problem import get_problem_by_id
from app.database import get_db
from ..models.problem_ref import ProblemReference
from app.group.models.group import Group
from app.group.models.group_member import GroupUser
from app.problem.models.problem import Problem

from ..schemas import ProblemReferenceCreate, ProblemReferenceGetRequest, ProblemShowResponse, ProblemPointsUpdateRequest, ProblemPointsUpdateResponse
from app.security import get_current_user

router = APIRouter(
    prefix="/problems_ref"
)

"""
ProblemReference API 는
    문제집에 문제 생성할 때 참조 용으로 사용
"""

@router.post("")
async def create_problem_ref_endpoint(
        problem_ref: ProblemReferenceCreate,
        current_user: Annotated[dict, Depends(get_current_user)],
        db: AsyncSession = Depends(get_db)
):
    # 그룹장 권한 확인
    if not await is_group_owner(db, problem_ref.group_id, current_user["sub"]):
        raise HTTPException(status_code=403, detail="너 그룹장 아니야 ~")

    try:
        await bulk_create_problem_refs(
            db=db,
            group_id=problem_ref.group_id,
            workbook_id=problem_ref.workbook_id,
            problem_ids=problem_ref.problem_id,
            points=problem_ref.points
        )
        return {"message": "문제가 성공적으로 연결되었습니다."}

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"문제 연결 중 오류 발생: {str(e)}")


@router.post("/get", response_model=List[ProblemShowResponse], status_code=status.HTTP_200_OK)
async def read_problem_ref_endpoint(
    request_data: ProblemReferenceGetRequest,
    current_user: dict = Depends(get_current_user),  # 필요 없으면 제거
    db: AsyncSession = Depends(get_db),
):
    return await read_problem_ref_crud(db, request_data)


@router.patch("/edit_points/{group_id}/{workbook_id}/{problem_id}", response_model=ProblemPointsUpdateResponse)
async def update_problem_points_endpoint(
    group_id: int,
    workbook_id: int,
    problem_id: int,
    points_update: ProblemPointsUpdateRequest,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    # 1. 기존 참조 가져오기
    old_ref = await get_problem_ref_by_ids(db, group_id, workbook_id, problem_id)

    # 2. soft delete 처리
    old_ref.is_deleted = True
    old_ref.deleted_at = datetime.now()
    await db.commit()

    # 3. 새 참조 생성
    new_ref = ProblemReference(
        group_id=group_id,
        workbook_id=workbook_id,
        problem_id=problem_id,
        points=points_update.points
    )
    db.add(new_ref)
    await db.commit()
    await db.refresh(new_ref)

    return ProblemPointsUpdateResponse(
        message="Points updated successfully (new reference created)",
        problem_id=new_ref.problem_id,
        updated_points=new_ref.points
    )

@router.delete("/{group_id}/{workbook_id}/{problem_id}")
async def delete_problem_ref_endpoint(
    group_id: int,
    workbook_id: int,
    problem_id: int,
    current_user: Annotated[dict, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    problem = await get_problem_by_id(db, problem_id)

    if problem is None:
        raise HTTPException(status_code=404, detail="Problem not found")

    if problem.maker_id != current_user["sub"]:
        raise HTTPException(status_code=403, detail="No permission to delete this problem")

    result = await delete_problem_ref_by_ids(db, group_id, workbook_id, problem_id)
    return {"detail": "Problem Ref deleted", "problem_ref": result}