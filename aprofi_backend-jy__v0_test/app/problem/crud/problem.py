from fastapi import HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import func
from sqlalchemy import update
from typing import Union, Any, Dict
from ..models.problem import Problem
from ..models.coding_problem import CodingProblem
from ..models.multiple_choice_problem import MultipleChoiceProblem
from ..models.short_answer_problem import ShortAnswerProblem
from ..models.subjective_problem import SubjectiveProblem
from ..schemas import CodingProblemResponseGet, MultipleChoiceProblemResponseGet, ShortAnswerProblemResponseGet, SubjectiveProblemResponseGet
from ..problem_type_Union import GetProblemResponseUnion, UpdateProblemRequestUnion
import logging
from ..models.problem import ProblemTypeEnum
from ..schemas import ProblemTypeEnum as schemaEnum
logger = logging.getLogger(__name__)

async def create_coding_problem(db: AsyncSession, data: CodingProblem) -> CodingProblem:
    db.add(data)
    await db.commit()
    await db.refresh(data)
    return data

async def create_multiple_choice_problem(db: AsyncSession, data: MultipleChoiceProblem) -> MultipleChoiceProblem:
    db.add(data)
    await db.commit()
    await db.refresh(data)
    return data

async def create_short_answer_problem(db: AsyncSession, data: ShortAnswerProblem) -> ShortAnswerProblem:
    db.add(data)
    await db.commit()
    await db.refresh(data)
    return data

async def create_subjective_problem(db: AsyncSession, data: SubjectiveProblem) -> SubjectiveProblem:
    db.add(data)
    await db.commit()
    await db.refresh(data)
    return data
#_____________________________________________________________________________________
def normalize_problem_type(raw) -> ProblemTypeEnum:
    try:
        # 이미 Enum인 경우
        if isinstance(raw, ProblemTypeEnum):
            return raw

        # Enum 클래스의 멤버를 문자열로 넣는 경우
        if isinstance(raw, str):
            return ProblemTypeEnum(raw)

        # Enum 멤버를 Enum으로 감쌌을 때 (예: ProblemTypeEnum.coding 같은)
        if hasattr(raw, "value") and raw.value in ProblemTypeEnum._value2member_map_:
            return ProblemTypeEnum(raw.value)

        raise ValueError(f"알 수 없는 문제 유형 값: {raw}")

    except ValueError:
        logger.error(f"[문제 유형 매핑 실패] 입력값: {raw}, 타입: {type(raw)}")
        raise HTTPException(status_code=500, detail="알 수 없는 문제 유형입니다.")
#___________________________________________________________________________________

def _as_list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]

def _normalize_rating_mode(pt: ProblemTypeEnum, v: Any) -> str:
    s = (str(v).strip().lower() if v is not None else "")
    if pt in (ProblemTypeEnum.coding, ProblemTypeEnum.debugging):
        return s if s in {"space", "regex", "hard", "none"} else "none"
    if pt in (ProblemTypeEnum.multiple_choice, ProblemTypeEnum.short_answer):
        return s if s in {"exact", "partial", "soft", "none"} else "none"
    if pt is ProblemTypeEnum.subjective:
        # 스키마가 active/deactive 임. 오타(deactivate) 주의!
        return s if s in {"active", "deactive"} else "active"
    return "none"

def transform_problem_to_response(problem: Problem) -> GetProblemResponseUnion:
    # problem.problem_type 가 Enum/str 섞일 수 있으므로 안전히 Enum으로
    try:
        pt = ProblemTypeEnum(problem.problem_type.value if hasattr(problem.problem_type, "value") else problem.problem_type)
    except ValueError:
        raise ValueError(f"지원되지 않는 문제 유형입니다: {problem.problem_type}")

    # 공통 필드 보정
    tags = _as_list(getattr(problem, "tags", None))
    problem_condition = _as_list(getattr(problem, "problem_condition", None))
    difficulty = getattr(problem, "difficulty", None)
    description = getattr(problem, "description", None)
    created_at = getattr(problem, "created_at", None)
    rating_mode = _normalize_rating_mode(pt, getattr(problem, "rating_mode", None))

    if pt in (ProblemTypeEnum.coding, ProblemTypeEnum.debugging):
        # 타입별 필드 집합
        reference_codes = _as_list(getattr(problem, "reference_codes", None))
        base_code = _as_list(getattr(problem, "base_code", None))
        test_cases = _as_list(getattr(problem, "test_cases", None))

        if pt is ProblemTypeEnum.coding:
            # 코딩: reference_codes 사용, base_code는 빈 배열로 강제
            payload_reference_codes = reference_codes
            payload_base_code = []
        else:
            # 디버깅: base_code 사용, reference_codes는 빈 배열로 강제
            payload_reference_codes = []
            payload_base_code = base_code

        return CodingProblemResponseGet(
            problem_id=problem.problem_id,
            maker_id=problem.maker_id,
            title=problem.title,
            description=description,
            difficulty=difficulty,
            tags=tags,
            problem_condition=problem_condition,
            created_at=created_at,
            problemType=pt.value,                 # 한글 Enum이면 그대로 value
            rating_mode=rating_mode,
            reference_codes=payload_reference_codes,   # 항상 list
            test_cases=test_cases,           # 항상 list
            base_code=payload_base_code,     # 항상 list (코딩은 [], 디버깅은 리스트)
        )

    if pt is ProblemTypeEnum.multiple_choice:
        options = _as_list(getattr(problem, "options", None))
        correct_answers = _as_list(getattr(problem, "correct_answers", None))

        return MultipleChoiceProblemResponseGet(
            problem_id=problem.problem_id,
            maker_id=problem.maker_id,
            title=problem.title,
            description=description,
            difficulty=difficulty,
            tags=tags,
            created_at=created_at,
            problemType=pt.value,
            rating_mode=rating_mode,
            options=options,                     # list
            correct_answers=correct_answers,     # list[int]
        )

    if pt is ProblemTypeEnum.short_answer:
        answer_text = _as_list(getattr(problem, "answer_text", None))
        grading_criteria = _as_list(getattr(problem, "grading_criteria", None))

        return ShortAnswerProblemResponseGet(
            problem_id=problem.problem_id,
            maker_id=problem.maker_id,
            title=problem.title,
            description=description,
            difficulty=difficulty,
            tags=tags,
            created_at=created_at,
            problemType=pt.value,
            rating_mode=rating_mode,
            answer_text=answer_text,                 # list[str]
            grading_criteria=grading_criteria,       # list[str]
        )

    if pt is ProblemTypeEnum.subjective:
        # 스키마가 str 이라면 첫 요소만 사용
        raw_answer = getattr(problem, "answer_text", None)
        if isinstance(raw_answer, list):
            answer_text = (raw_answer[0] if raw_answer else "")
        else:
            answer_text = (raw_answer or "")

        grading_criteria = _as_list(getattr(problem, "grading_criteria", None))

        return SubjectiveProblemResponseGet(
            problem_id=problem.problem_id,
            maker_id=problem.maker_id,
            title=problem.title,
            description=description,
            difficulty=difficulty,
            tags=tags,
            created_at=created_at,
            problemType=pt.value,
            rating_mode=rating_mode.replace("deactivate", "deactive") if rating_mode else "active",  # ✅ 오타 방지
            answer_text=answer_text,               # str
            grading_criteria=grading_criteria,     # list[str] | None
        )

    raise ValueError("지원되지 않는 문제 유형입니다.")
#___________________________________________________________________________________
async def soft_delete_problem(db: AsyncSession, problem_id: int) -> None:
    await db.execute(
        update(Problem)
        .where(Problem.problem_id == problem_id)
        .values(
            is_deleted=True,
            deleted_at=datetime.now()
        )
    )
    await db.commit()

def create_problem_instance_from_update(old_problem: Problem, updates: UpdateProblemRequestUnion) -> Problem:
    try:
        problem_type = translate_problem_type(updates.problemType)  # 문자열 → Enum 변환
    except ValueError:
        raise ValueError(f"지원되지 않는 문제 유형입니다: {updates.problemType}")

    common_fields = {
        "maker_id": old_problem.maker_id,
        "title": updates.title or old_problem.title,
        "description": updates.description or old_problem.description,
        "difficulty": updates.difficulty or old_problem.difficulty,
        "problem_type": problem_type,
        "tags": updates.tags or old_problem.tags,
        "prev_problem_id": old_problem.problem_id,
    }

    match problem_type:
        case ProblemTypeEnum.coding | ProblemTypeEnum.debugging:
            return CodingProblem(
                **common_fields,
                rating_mode=updates.rating_mode,
                problem_condition=updates.problem_condition or [],
                reference_codes=[rc.model_dump() for rc in updates.reference_codes or []],
                test_cases=[tc.model_dump() for tc in updates.test_cases or []],
                base_code=[{"language": "python", "code": updates.base_code}] if updates.base_code else []
            )

        case ProblemTypeEnum.multiple_choice:
            return MultipleChoiceProblem(
                **common_fields,
                options=updates.options,
                correct_answers=updates.correct_answers
            )

        case ProblemTypeEnum.short_answer:
            return ShortAnswerProblem(
                **common_fields,
                rating_mode=updates.rating_mode,
                answer=updates.answer_texts,
                grading_criteria=updates.grading_criteria
            )

        case ProblemTypeEnum.subjective:
            return SubjectiveProblem(
                **common_fields,
                rating_mode=updates.rating_mode,
                grading_criteria=updates.grading_criteria,
                answer=[None]  # 주관식은 답변 없음
            )

        case _:
            raise ValueError("지원되지 않는 문제 유형입니다.")

def translate_problem_type(schema_type: schemaEnum) -> ProblemTypeEnum:
    mapping = {
        schemaEnum.coding: ProblemTypeEnum.coding,
        schemaEnum.debugging: ProblemTypeEnum.debugging,
        schemaEnum.multiple_choice: ProblemTypeEnum.multiple_choice,
        schemaEnum.short_answer: ProblemTypeEnum.short_answer,
        schemaEnum.subjective: ProblemTypeEnum.subjective,
    }
    try:
        return mapping[schema_type]
    except KeyError:
        raise ValueError(f"지원되지 않는 문제 유형입니다: {schema_type}")
#___________________________________________________________________________________

async def get_problem_by_id(db: AsyncSession, problem_id: int) -> Problem:
    result = await db.execute(
        select(Problem).where(
            (Problem.problem_id == problem_id) &
            (Problem.is_deleted.is_(False))
        )
    )
    problem = result.scalar_one_or_none()

    if not problem:
        raise ValueError(f"Problem with id {problem_id} not found or has been deleted")

    return problem

async def delete_problem(db: AsyncSession, problem_id: int) -> Problem:
    try:
        result = await db.execute(
            update(Problem)
            .where(Problem.problem_id == problem_id)
            .values(
                is_deleted=True,
                deleted_at=datetime.now()
            )
            .returning(Problem)
        )
        deleted_problem = result.scalar_one_or_none()
        await db.commit()

        if not deleted_problem:
            raise ValueError(f"Problem with id {problem_id} not found or already deleted")

        return deleted_problem
    except Exception as e:
        await db.rollback()
        raise e