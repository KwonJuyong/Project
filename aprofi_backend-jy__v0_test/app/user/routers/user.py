from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from fastapi import Response
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated
from app.database import get_db
from ..models.User import User
from ..schemas import LoginRequest, RegisterRequest, ChangePasswordRequest
from ..crud.user import create_user, check_user
from app.security import create_access_token, get_current_user, verify_password, hash_password
from sqlalchemy.future import select

ACCESS_TOKEN_EXPIRE_MINUTES = 90

router = APIRouter(
    prefix="/user"
)


# 전체 사용자 조회 (관리자용)
@router.get("")
async def get_users(db: AsyncSession = Depends(get_db)):
    statement = select(User)
    results = await db.execute(statement)
    return results.scalars().all()


@router.post("/register")
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        msg = await create_user(db, request)
        return msg  # TODO return 값이 str임
    except ValueError as e:
        raise HTTPException(status_code=401, detail=e)  # TODO 수정 필요



@router.post("/login")
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    try:
        user: User = await check_user(db, request.user_id, request.password)

        # 토큰 생성
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(data={"sub": user.user_id}, expires_delta=access_token_expires)

        # 응답 본문에 토큰 포함
        return {
            "message": "Login successful",
            "access_token": access_token
        }
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.put("/change_password")
async def change_password(request: ChangePasswordRequest, db: AsyncSession = Depends(get_db)):
    try:
        # 유저 검색
        stmt = select(User).where(User.user_id == request.user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다.")

        # 현재 비밀번호 검증 (해시 비교)
        if not verify_password(request.current_password, user.hashed_password):
            raise HTTPException(status_code=400, detail="현재 비밀번호가 일치하지 않습니다.")

        # 새 비밀번호를 해싱하여 저장
        user.hashed_password = hash_password(request.new_password)
        await db.commit()

        return {"message": "비밀번호가 성공적으로 변경되었습니다."}

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail="서버 오류 발생")


# Authorization 헤더에 포함된 토큰을 통해 인증된 사용자 정보를 반환
@router.get("/me")
async def read_own_user(
        current_user: Annotated[User, Depends(get_current_user)]
):
    return {"user_id": current_user["sub"]}