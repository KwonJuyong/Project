from fastapi import HTTPException
from fastapi.responses import JSONResponse

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func, and_
from sqlalchemy import update
from ..schemas import WorkbookUpdateRequest
from ..models.workbook import Workbook
from datetime import datetime
from app.problem_ref.models.problem_ref import ProblemReference
from app.problem.models.problem import Problem

async def create_workbook(db: AsyncSession, orm_workbook: Workbook) -> Workbook:
    db.add(orm_workbook)
    await db.commit()
    await db.refresh(orm_workbook)
    return orm_workbook


async def get_workbook_by_workbook_id(db: AsyncSession, workbook_id: int):
    result = await db.execute(
        select(Workbook).where(
            (Workbook.workbook_id == workbook_id) &
            (Workbook.is_deleted == False)  # Use is_deleted instead of deleted_at
        )
    )
    return result.scalar_one_or_none()


async def delete_workbook(db: AsyncSession, workbook_id: int):
    result = await db.execute(select(Workbook).where(Workbook.workbook_id == workbook_id))
    workbook = result.scalar_one_or_none()

    if not workbook:
        raise HTTPException(
            status_code=404,
            detail={
                "msg": f"workbook_id가 {workbook_id}인 문제지가 존재하지 않아요..."
            })

    await db.execute(
        update(Workbook)
        .where(Workbook.workbook_id == workbook_id)
        .values(deleted_at=func.now(), is_deleted=True)
    )
    await db.commit()
    return JSONResponse(
        status_code=200,
        content={
            "msg": f"문제지({workbook_id})가 정상적으로 삭제 되었습니다..."
        }
    )


async def update_workbook(
    db: AsyncSession,
    workbook: Workbook,
    update_data: WorkbookUpdateRequest
):
    # 1. 기존 workbook soft delete
    workbook.is_deleted = True
    workbook.deleted_at = datetime.now()
    await db.flush()

    # 2. 새로운 workbook 객체 생성
    update_dict = update_data.model_dump()
    
    new_workbook = Workbook(
        workbook_name=update_dict["workbook_name"].strip(),
        group_id=workbook.group_id, 
        description=update_dict["description"].strip(),
        is_test_mode=workbook.is_test_mode, 
        test_start_time=update_dict.get("test_start_time"),
        test_end_time=update_dict.get("test_end_time"),
        start_date=update_dict.get("publication_start_time"),
        end_date=update_dict.get("publication_end_time")
    )

    db.add(new_workbook)
    await db.flush()
    await db.commit()
    await db.refresh(new_workbook)

    return new_workbook.workbook_id


async def count_problems_in_workbook(db: AsyncSession, workbook_id: int) -> int:
    stmt = (
        select(func.count())
        .select_from(ProblemReference)
        .join(Problem, Problem.problem_id == ProblemReference.problem_id)
        .where(
            and_(
                ProblemReference.workbook_id == workbook_id,
                ProblemReference.is_deleted.is_(False),
                Problem.is_deleted.is_(False),
            )
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one()


async def sum_workbook_points(db: AsyncSession, workbook_id: int) -> int:
    stmt = (
        select(func.coalesce(func.sum(ProblemReference.points), 0))
        .where(
            and_(
                ProblemReference.workbook_id == workbook_id,
                ProblemReference.is_deleted.is_(False),
            )
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one()