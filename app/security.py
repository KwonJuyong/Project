from datetime import datetime, timedelta
from jose import jwt, JWTError
import os
from passlib.context import CryptContext
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Security
from fastapi.security import OAuth2PasswordBearer

load_dotenv()

SECRET_KEY = "a2xqbDMxbmtsc2RhajRuMWprYmtkc2EjIUAjIUBEU2FkanNhZGphNA41ASF2h41Fbi10S1h14BkgSAg41n9HG1AFfdds12A"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = "90"
REFRESH_TOKEN_EXPIRE_DAYS = "7"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 비밀번호 해싱으로 저장
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

# 비밀번호 검증
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

# JWT Access Token 생성
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta if expires_delta else timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# # JWT Refresh Token 생성
# def create_refresh_token(data: dict):
#     expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
#     return jwt.encode({"sub": data["sub"], "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)

# JWT 토큰 검증
def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# 현재 로그인된 사용자 가져오기
async def get_current_user(token: str = Security(oauth2_scheme)):
    credentials_exception = HTTPException(status_code=401, detail="Could not validate credentials")
    
    payload = verify_token(token)
    if payload is None:
        raise credentials_exception
    return payload
