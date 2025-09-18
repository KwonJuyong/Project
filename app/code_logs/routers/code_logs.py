from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.code_logs.schemas import CodeLogsRequest, CodeLogsResponse
from app.code_logs.crud.code_logs import code_logs_create_crud, code_logs_get_by_solve_id_crud

router = APIRouter(
    prefix="/code_logs"
    )

@router.post("")
async def code_logs_create(
    payload: CodeLogsRequest, db: AsyncSession = Depends(get_db)
):
    count = await code_logs_create_crud(db, payload)
    await db.commit()
    return count

@router.get("/{solve_id}", response_model=List[CodeLogsResponse])
async def code_logs_get_by_solve_id(
    solve_id: int, db: AsyncSession = Depends(get_db)
):
    return await code_logs_get_by_solve_id_crud(db, solve_id)