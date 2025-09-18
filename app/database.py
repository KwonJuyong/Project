from sqlalchemy import text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import MetaData
from sqlalchemy.pool import NullPool
from sqlalchemy.exc import OperationalError
import asyncio
from dotenv import load_dotenv
import os

# .env 파일 로드
load_dotenv()

# 아이디와 비번 가져오기
DB_ADMIN_ID = os.getenv("DB_ADMIN_ID")
DB_ADMIN_PW = os.getenv("DB_ADMIN_PW")

# DATABASE URL 생성 (아이디와 비번만 숨기고 나머지는 코드에 작성)
# DATABASE_URL = f"postgresql+asyncpg://{DB_ADMIN_ID}:{DB_ADMIN_PW}@localhost:4856/aprofi"
DATABASE_URL = os.getenv("DATABASE_URL")

# 엔진 생성
engine = create_async_engine(DATABASE_URL, echo=True)
# 세션 팩토리 생성
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # 커밋 후 객체 만료 방지
    autocommit=False,
    autoflush=False,
)

# Base 클래스 생성
Base = declarative_base()

# 데이터베이스 세션 의존성
async def get_db():
    """데이터베이스 세션 의존성"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# 데이터베이스 초기화
async def init_db():
    # 모델 import (반드시 필요!)
    from app.user.models import User
    from app.group.models.group import Group
    from app.group.models.group_member import GroupUser
    from app.group.models.group_request import GroupUserRequest
    from app.problem.models.problem import Problem
    from app.problem.models.coding_problem import CodingProblem
    from app.problem.models.multiple_choice_problem import MultipleChoiceProblem
    from app.problem.models.short_answer_problem import ShortAnswerProblem
    from app.problem.models.subjective_problem import SubjectiveProblem
    from app.problem_ref.models.problem_ref import ProblemReference
    from app.workbook.models.workbook import Workbook
    from app.submission.models.submisson import Submission
    from app.submission.models.coding import CodingSubmission
    from app.submission.models.multiple_choice import MultipleChoiceSubmission
    from app.submission.models.short_answer import ShortAnswerSubmission
    from app.submission.models.subjective import SubjectiveSubmission
    from app.submission.models.testcases_excution_log import TestcasesExecutionLog
    from app.submission.models.submission_score import SubmissionScore
    from app.code_logs.models.coding_submission_log import CodingSubmissionLog
    from app.comment.models.comment import Comment
    
    max_retries = 10
    for attempt in range(max_retries):
        try:
            async with engine.begin() as conn:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                await conn.run_sync(Base.metadata.create_all)
            print("DB 연결 및 초기화 성공")
            break
        except (OperationalError, OSError) as e:  # ✅ OSError 추가
            print(f"DB 연결 재시도 {attempt+1}/{max_retries}회: {e}")
            await asyncio.sleep(3)
    else:
        raise RuntimeError("DB 연결 실패: 최대 재시도 초과")
