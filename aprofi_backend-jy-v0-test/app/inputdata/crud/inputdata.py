# app/inputdata/crud.py
from __future__ import annotations
from typing import Any, Dict
import json

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.problem.models.coding_problem import CodingProblem, DebuggingProblem
from app.problem.models.multiple_choice_problem import MultipleChoiceProblem
from app.problem.models.short_answer_problem import ShortAnswerProblem
from app.problem.models.subjective_problem import SubjectiveProblem

PROBLEM_MODEL_MAP: Dict[str, Any] = {
    "coding": CodingProblem, "코딩": CodingProblem,
    "debugging": DebuggingProblem, "디버깅": DebuggingProblem,
    "multiple_choice": MultipleChoiceProblem, "객관식": MultipleChoiceProblem,
    "short_answer": ShortAnswerProblem, "단답형": ShortAnswerProblem,
    "subjective": SubjectiveProblem, "주관식": SubjectiveProblem,
}

ALLOWED_FIELDS_MAP: Dict[str, set[str]] = {
    # ⛔ 코딩에는 base_code 전달하지 않음 (헷갈림 방지)
    "coding": {"title","description","difficulty","tags","problem_condition","reference_codes","test_cases","rating_mode"},
    "코딩":   {"title","description","difficulty","tags","problem_condition","reference_codes","test_cases","rating_mode"},
    # ⛔ 디버깅에는 reference_codes 전달하지 않음
    "debugging": {"title","description","difficulty","tags","problem_condition","test_cases","rating_mode","base_code"},
    "디버깅":   {"title","description","difficulty","tags","problem_condition","test_cases","rating_mode","base_code"},
    "multiple_choice": {"title","description","difficulty","tags","options","correct_answers","rating_mode"},
    "객관식":          {"title","description","difficulty","tags","options","correct_answers","rating_mode"},
    "short_answer":    {"title","description","difficulty","tags","answer_text","rating_mode","grading_criteria"},
    "단답형":          {"title","description","difficulty","tags","answer_text","rating_mode","grading_criteria"},
    "subjective":      {"title","description","difficulty","tags","answer_text","rating_mode","grading_criteria"},
    "주관식":          {"title","description","difficulty","tags","answer_text","rating_mode","grading_criteria"},
}

def _as_list(v: Any) -> list:
    if v is None: return []
    if isinstance(v, list): return v
    if isinstance(v, str):
        s = v.strip()
        if not s: return []
        try:
            p = json.loads(s)
            return p if isinstance(p, list) else ([p] if p else [])
        except Exception:
            return [v]
    return [v]

def _as_lower(v: Any, default: str = "") -> str:
    s = "" if v is None else str(v).strip()
    return s.lower() if s else default

def _normalize_rating_mode(problem_type: str, v: Any) -> str:
    s = _as_lower(v)
    if problem_type in ("coding","코딩","debugging","디버깅"):
        return s if s in {"space","regex","hard","none"} else "none"
    if problem_type in ("multiple_choice","객관식","short_answer","단답형"):
        return s if s in {"exact","partial","soft","none"} else "none"
    if problem_type in ("subjective","주관식"):
        return s if s in {"active","deactive"} else "active"
    return "none"

async def create_problem(db: AsyncSession, problem_data, maker_id: str):
    # 1) 타입/모델
    problem_type: str = getattr(problem_data, "problemType", None)
    if problem_type not in PROBLEM_MODEL_MAP:
        raise HTTPException(status_code=400, detail=f"Unsupported problemType: {problem_type}")
    model_cls = PROBLEM_MODEL_MAP[problem_type]
    allowed = ALLOWED_FIELDS_MAP[problem_type]

    # 2) dict 추출
    try:
        raw: Dict[str, Any] = problem_data.model_dump()
    except Exception:
        raw = problem_data.dict()

    # 3) 화이트리스트 필터
    data: Dict[str, Any] = {k: v for k, v in raw.items() if k in allowed}

    # 4) 공통 배열 보정
    if "tags" in allowed: data["tags"] = _as_list(data.get("tags"))
    if "problem_condition" in allowed: data["problem_condition"] = _as_list(data.get("problem_condition"))
    if "test_cases" in allowed: data["test_cases"] = _as_list(data.get("test_cases"))
    if "grading_criteria" in allowed: data["grading_criteria"] = _as_list(data.get("grading_criteria"))

    # 5) 타입별 정책
    if problem_type in ("coding","코딩"):
        # 코딩은 reference_codes만 사용
        data["reference_codes"] = _as_list(data.get("reference_codes"))
        data["rating_mode"] = _normalize_rating_mode(problem_type, data.get("rating_mode"))
        # 혹시 들어왔다면 제거
        data.pop("base_code", None)

    elif problem_type in ("debugging","디버깅"):
        base_code = _as_list(data.get("base_code"))
        if not base_code:
            raise HTTPException(status_code=400, detail="디버깅 문제는 base_code가 최소 1개 필요합니다.")
        data["base_code"] = base_code
        data["rating_mode"] = _normalize_rating_mode(problem_type, data.get("rating_mode"))
        # 혹시 들어왔다면 제거
        data.pop("reference_codes", None)

    elif problem_type in ("multiple_choice","객관식"):
        data["options"] = _as_list(data.get("options"))
        data["correct_answers"] = _as_list(data.get("correct_answers"))
        data["rating_mode"] = _normalize_rating_mode(problem_type, data.get("rating_mode"))

    elif problem_type in ("short_answer","단답형"):
        data["answer_text"] = _as_list(data.get("answer_text"))
        data["rating_mode"] = _normalize_rating_mode(problem_type, data.get("rating_mode"))

    elif problem_type in ("subjective","주관식"):
        v = data.get("answer_text")
        if isinstance(v, list):
            data["answer_text"] = v[0] if v else ""
        data["rating_mode"] = _normalize_rating_mode(problem_type, data.get("rating_mode"))

    # 6) INSERT (flush 전에 안전 가드)
    try:
        problem_obj = model_cls(**data, maker_id=maker_id)

        # 🔒 안전 가드: 코딩인데 reference_codes가 None이면 빈 리스트로 강제
        if isinstance(problem_obj, CodingProblem) and getattr(problem_obj, "reference_codes", None) is None:
            problem_obj.reference_codes = []

        # 🔒 안전 가드: 디버깅인데 base_code가 None이면 막기
        if isinstance(problem_obj, DebuggingProblem) and not getattr(problem_obj, "base_code", None):
            raise HTTPException(status_code=400, detail="디버깅 문제는 base_code가 최소 1개 필요합니다.")

        db.add(problem_obj)
        await db.flush()   # 여기서 실패하면 즉시 에러 확인 가능
        await db.commit()
        await db.refresh(problem_obj)
        return problem_obj

    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Integrity error: {str(e.orig)}")
