from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.register_checker.schemas import RegisterCheckRequest, RegisterCheckResponse
from app.register_checker.crud.register_checker import is_user_exist, is_email_exist

router = APIRouter(prefix="/register_checker")

@router.post("/", response_model=RegisterCheckResponse)
async def register_checker(data: RegisterCheckRequest, db: AsyncSession = Depends(get_db)):
    is_user_exist_result = True
    is_email_exist_result = True

    try:
        await is_user_exist(db, data.user_id)
    except ValueError:
        is_user_exist_result = False

    try:
        await is_email_exist(db, data.email)
    except ValueError:
        is_email_exist_result = False

    return RegisterCheckResponse(
        is_user_exist=is_user_exist_result,
        is_email_exist=is_email_exist_result
    )
