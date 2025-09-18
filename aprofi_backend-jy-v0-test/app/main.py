from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from app.user.routers import user
from app.group.routers import group, group_request, group_member
from app.workbook.routers import workbook
from app.problem.routers import problem
from app.problem_ref.routers import problem_ref
from app.inputdata.routers import inputdata
from app.submission.routers import submission
from app.comment.routers import comment
from app.code_logs.routers import code_logs
import logging
from app.database import init_db
from app.user_session.router.presence import router as presence_router
from app.user_session.crud.redis_presence import scheduled_job
from app.register_checker.routers import register_checker  

app = FastAPI()

origins = [
    "http://localhost:3000",
    "https://aprofi-test.vercel.app",
    "https://aprofi.vercel.app"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# 데이터 베이스 테이블 생성
@app.on_event("startup")
async def startup():
    await init_db()
    asyncio.create_task(scheduled_job())


@app.get("/")
async def root():
    return {"root": 200}


# 라우터 등록
app.include_router(user.router, prefix="/api", tags=["user"])
app.include_router(group.router, prefix="/api", tags=["group"])
app.include_router(group_request.router, prefix="/api", tags=["group_request"])
app.include_router(group_member.router, prefix="/api", tags=["group_member"])
app.include_router(workbook.router, prefix="/api", tags=["workbook"])
app.include_router(problem.router, prefix="/api", tags=["problem"])
app.include_router(problem_ref.router, prefix="/api", tags=["problem_ref"])
app.include_router(inputdata.router, prefix="/api", tags=["inputdata"])
app.include_router(submission.router, prefix="/api", tags=["submission"])
app.include_router(comment.router, prefix="/api", tags=["comment"])
app.include_router(code_logs.router, prefix="/api", tags=["code_logs"])
app.include_router(presence_router, tags=["presence"])


# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# SQLAlchemy 로깅 설정
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
logging.getLogger('sqlalchemy.pool').setLevel(logging.INFO)

# 중복확인
app.include_router(register_checker.router, prefix="/api")