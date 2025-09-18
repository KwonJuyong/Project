# app/submission/crud/submission.py
from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple, TypedDict, cast, Literal
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, case, literal, desc
from sqlalchemy.orm import with_polymorphic
from fastapi import HTTPException, status
from dataclasses import is_dataclass, asdict
from datetime import datetime
import json
import inspect



from app.submission.schemas import (
    SolveRequestUnion, ProblemTypeKOR,
    CodingSolveRequest, DebuggingSolveRequest,
    MultipleChoiceSolveRequest, ShortAnswerSolveRequest, SubjectiveSolveRequest,
    TestCaseInput, SubjectiveSolveResponseMe, RunCodeRequest, RunCodeResponse, TestCase, OverallStatus, CodingTestCase, CodingTestResult, TestCaseResult
)

# 문제/레퍼런스 모델
from app.problem.models.problem import Problem
from app.problem.models.coding_problem import CodingProblem, DebuggingProblem
from app.problem.models.multiple_choice_problem import MultipleChoiceProblem
from app.problem.models.short_answer_problem import ShortAnswerProblem
from app.problem.models.subjective_problem import SubjectiveProblem, AutoRatingMode
from app.problem_ref.models.problem_ref import ProblemReference
from app.group.models.group import Group
from app.workbook.models.workbook import Workbook

# 제출/점수 모델
from app.submission.models.submisson import Submission
from app.submission.models.coding import (
    CodingSubmission,
    DebuggingSubmission,
    ExecutionStatus as ModelExecStatus,   # 모델 Enum 사용
)
from app.submission.models.multiple_choice import MultipleChoiceSubmission
from app.submission.models.short_answer import ShortAnswerSubmission
from app.submission.models.subjective import SubjectiveSubmission
from app.submission.models.submission_score import SubmissionScore

# 채점기/유틸
from app.submission.services.code_compiler import (
    CodeRunner,
    RatingMode as RunnerRatingMode,
)
from app.submission.services.gpt_problem_condition_checker import GPTConditionChecker
from app.submission.services.problem_condition_checker import ConditionChecker, ProblemConditionCheck
from app.submission.services.condition_utils import normalize_condition_checks, distribute_condition_scores

from app.submission.services.problem_Normalization import problem_Normalization
from app.submission.services.ai_feedback import AIFeedbackService

from app.submission.models.testcases_excution_log import TestcasesExecutionLog, languageEnum
from app.submission.schemas import (
    RunCodeRequest, RunCodeResponse, TestCase, getAllSubmissionsResponse, SubmissionGetScoreResponse,
    TestCaseInput,  # ← 러너가 기대하는 TC 타입
)

class RubricItem(TypedDict):
    criterion: str
    weight: float

Rubric = List[RubricItem]

ShortMode = Literal["exact", "partial", "soft"]

def _ensure_int_list(raw: Any) -> List[int]:
    """Any → list[int]"""
    if raw is None:
        return []
    if isinstance(raw, list):
        out: List[int] = []
        for x in raw:
            try:
                out.append(int(x))
            except Exception:
                continue
        return out
    try:
        return [int(raw)]
    except Exception:
        return []

def _ensure_str_list(raw: Any) -> List[str]:
    """Any → list[str]"""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if x is not None and str(x).strip() != ""]
    s = str(raw).strip()
    return [s] if s else []

def _normalize_short_answer_mode(raw: Any) -> ShortMode:
    """Any → Literal['exact','partial','soft']"""
    s = str(raw or "exact").strip().lower()
    if s in ("exact", "partial", "soft"):
        return cast(ShortMode, s)
    return "exact"

# ---------- 내부 DTO ----------
@dataclass
class SolveResultDTO:
    submission_id: int
    problem_id: int
    created_at: datetime
    is_correct: bool


# ---------- 유틸 매핑 ----------
KOR_TO_IDENTITY: dict[ProblemTypeKOR, str] = {
    ProblemTypeKOR.coding: "coding",
    ProblemTypeKOR.debugging: "debugging",
    ProblemTypeKOR.multiple_choice: "multiple_choice",
    ProblemTypeKOR.short_answer: "short_answer",
    ProblemTypeKOR.subjective: "subjective",
}

# 문자열로 들어오는 태그(한/영 혼용)를 표준 identity로 매핑
STR_TO_IDENTITY: dict[str, str] = {
    "코딩": "coding",
    "coding": "coding",
    "디버깅": "debugging",
    "debugging": "debugging",
    "객관식": "multiple_choice",
    "multiple_choice": "multiple_choice",
    "단답형": "short_answer",
    "short_answer": "short_answer",
    "주관식": "subjective",
    "subjective": "subjective",
}

def _resolve_identity_tag(tag: Any) -> Optional[str]:
    """ProblemTypeKOR(Enum) 또는 str(한/영)을 표준 identity(str)로 변환"""
    if isinstance(tag, ProblemTypeKOR):
        return KOR_TO_IDENTITY.get(tag)
    if isinstance(tag, str):
        key = tag.strip()
        # 영어는 소문자/언더스코어 표준화도 지원
        return STR_TO_IDENTITY.get(key) or STR_TO_IDENTITY.get(key.lower())
    return None

def _map_rating_mode(m: str | None) -> RunnerRatingMode:
    val = (m or "none").strip().lower()
    return {
        "hard": RunnerRatingMode.HARD,
        "space": RunnerRatingMode.SPACE,
        "regex": RunnerRatingMode.REGEX,
        "none": RunnerRatingMode.NONE,
    }.get(val, RunnerRatingMode.NONE)

def _decide_rating_mode_for_debugging(pb, requested_mode):
    """
    디버깅 문제용 채점 모드 결정 로직.
    - 요청이 있으면 우선
    - 없으면 문제에 정의된 기본값 또는 'hard' 등 프로젝트 규칙
    """
    if requested_mode:
        return requested_mode
    return getattr(pb, "rating_mode", None) or "hard"


def _decide_rating_mode_for_coding(pb, requested: str | None) -> RunnerRatingMode:
    """
    코딩 문제에서 expected_output이 하나도 없으면 채점 모드 강제로 NONE.
    """
    raw = getattr(pb, "test_cases", []) or []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw) or []
        except Exception:
            raw = []

    def _get_expected(tc) -> str:
        if isinstance(tc, dict):
            return str(tc.get("expected_output", "") or "")
        return str(getattr(tc, "expected_output", "") or "")

    has_any_expected = any(_get_expected(tc) != "" for tc in raw)
    # ★ 기대 출력이 하나도 없으면 비교 불가 → NONE으로 실행만
    return _map_rating_mode(requested) if has_any_expected else RunnerRatingMode.NONE


# ---------- 러너 싱글턴 ----------
_runner_singleton: Optional[CodeRunner] = None
def get_runner() -> CodeRunner:
    global _runner_singleton
    if _runner_singleton is None:
        _runner_singleton = CodeRunner()
    return _runner_singleton


# ---------- 러너 결과 표준화 ----------
def _normalize_runner_results(results: list) -> List[Dict[str, Any]]:
    """
    러너 결과(TestCase/Pydantic/데이터클래스/딕셔너리)를
    DB/응답에 공용으로 쓰기 좋은 list[dict]로 정규화한다.
    필수 키를 보강하고 타입을 안전 캐스팅한다.
    """
    def _to_dict(i: int, r: Any) -> Dict[str, Any]:
        # Pydantic v2
        if hasattr(r, "model_dump"):
            d = r.model_dump()
        # Pydantic v1
        elif hasattr(r, "dict"):
            d = r.dict()
        # dataclass
        elif is_dataclass(r):
            d = asdict(r)
        # dict
        elif isinstance(r, dict):
            d = r
        else:
            # 마지막 폴백: 속성 추출
            d = {
                "test_case_index": getattr(r, "test_case_index", i),
                "status": getattr(r, "status", None),
                "output": getattr(r, "output", None),
                "error": getattr(r, "error", None),
                "execution_time": getattr(r, "execution_time", 0.0),
                "memory_usage": getattr(r, "memory_usage", 0),
                "passed": getattr(r, "passed", None),
                "input": getattr(r, "input", None),
                "expected_output": getattr(r, "expected_output", None),
            }
        # 얕은 복사(원본 변형 방지)
        return dict(d)

    norm: List[Dict[str, Any]] = []

    for i, r in enumerate(results or []):
        d = _to_dict(i, r)

        # --- 인덱스/기본키 보강 ---
        # test_case_index
        try:
            tci = d.get("test_case_index", i)
            d["test_case_index"] = int(tci) if tci is not None else i
        except Exception:
            d["test_case_index"] = i

        # 문자열화 유틸
        def _s(x: Any) -> str:
            if x is None: return ""
            try: return str(x)
            except Exception: return ""

        # 숫자 캐스팅
        try:
            d["execution_time"] = float(d.get("execution_time") or 0.0)
        except Exception:
            d["execution_time"] = 0.0
        try:
            d["memory_usage"] = int(d.get("memory_usage") or 0)
        except Exception:
            d["memory_usage"] = 0

        # I/O 문자열화
        d["output"] = _s(d.get("output"))
        d["error"] = _s(d.get("error"))
        d["input"] = _s(d.get("input"))
        d["expected_output"] = _s(d.get("expected_output"))

        # --- status 정규화 ---
        st = d.get("status")
        st_str = ""
        if hasattr(st, "name"):
            st_str = _s(getattr(st, "name", "")).upper()
        elif hasattr(st, "value"):
            st_str = _s(getattr(st, "value", "")).upper()
        elif isinstance(st, str):
            st_str = st.upper().strip()
        else:
            st_str = ""  # 나중에 passed/error로 추론

        # passed 정규화(없으면 추론)
        passed = d.get("passed", None)
        if passed is None:
            if st_str in ("SUCCESS", "PASSED", "OK"):
                passed = True
            elif st_str in ("FAILED", "FAIL", "ERROR", "TIMEOUT"):
                passed = False
            else:
                # 출력/기대값이 모두 있으면 간단 추론
                if d["expected_output"] != "":
                    passed = (d["output"] == d["expected_output"])
                else:
                    # 기대값이 없고 에러도 없으면 통과로 간주
                    passed = (d["error"] == "")
        d["passed"] = bool(passed)

        # status 최종 결정
        if not st_str:
            if d["error"]:
                st_str = "ERROR"
            else:
                st_str = "SUCCESS" if d["passed"] else "FAILED"
        else:
            # 통일
            if st_str in ("OK", "PASSED"):
                st_str = "SUCCESS"
            elif st_str in ("FAIL",):
                st_str = "FAILED"
        d["status"] = st_str

        norm.append(d)

    return norm


class SolveService:
    PASSING_SCORE_DEFAULT = 60.0

    def __init__(self, db: AsyncSession, current_user: dict):
        self.db = db
        self.current_user = current_user

        # 컴파일러 싱글턴 사용
        self.compiler = get_runner()

        # 통합형 AI 피드백/점수 서비스
        self.ai = AIFeedbackService()


    def _normalize_rubric(self, raw: Any) -> Rubric:
        """grading_criteria → [{'criterion': str, 'weight': float}, ...], weight 합계=100.0"""

        def _default() -> Rubric:
            return [{"criterion": "내용의 타당성과 명료성", "weight": 100.0}]

        if raw is None:
            return _default()

        # ── str 입력: JSON 시도 → 실패 시 줄/콤마 분리 후 동일 가중치
        if isinstance(raw, str):
            s = raw.strip()
            if not s:
                return _default()
            try:
                raw = json.loads(s)
            except Exception:
                parts: List[str] = [p.strip() for line in s.splitlines() for p in line.split(",")]
                labels: List[str] = [p for p in parts if p]
                if not labels:
                    return _default()
                w = 100.0 / len(labels)
                return cast(Rubric, [{"criterion": label, "weight": float(w)} for label in labels])

        # ── list 입력
        if isinstance(raw, list):
            if not raw:
                return _default()

            # list[dict] → 그대로 기준/가중치 읽어 Rubric 작성
            if all(isinstance(x, dict) for x in raw):
                rubric_items: Rubric = []
                for d in raw:
                    crit = str(d.get("criterion") or d.get("name") or d.get("title") or "").strip()
                    if not crit:
                        continue
                    w_val = d.get("weight", d.get("score", d.get("points", None)))
                    try:
                        w = float(w_val) if w_val is not None else 1.0
                    except Exception:
                        w = 1.0
                    if w < 0:
                        w = 1.0
                    rubric_items.append({"criterion": crit, "weight": float(w)})
                if not rubric_items:
                    return _default()
                total = sum(i["weight"] for i in rubric_items)
                if total <= 0:
                    eq = 100.0 / len(rubric_items)
                    return cast(Rubric, [{"criterion": i["criterion"], "weight": float(eq)} for i in rubric_items])
                scale = 100.0 / total
                return cast(Rubric, [{"criterion": i["criterion"], "weight": round(i["weight"] * scale, 6)} for i in rubric_items])

            # list[str] → 동일 가중치로 Rubric 생성
            if all(isinstance(x, str) for x in raw):
                labels = [x.strip() for x in raw if x and x.strip()]
                if not labels:
                    return _default()
                w = 100.0 / len(labels)
                return cast(Rubric, [{"criterion": label, "weight": float(w)} for label in labels])

            # 혼합 리스트 → 문자열화 후 동일 가중치
            labels = [str(x).strip() for x in raw if str(x).strip()]
            if not labels:
                return _default()
            w = 100.0 / len(labels)
            return cast(Rubric, [{"criterion": label, "weight": float(w)} for label in labels])

        # ── dict 단일 항목
        if isinstance(raw, dict):
            crit = str(raw.get("criterion") or raw.get("name") or raw.get("title") or "").strip()
            if not crit:
                return _default()
            try:
                w = float(raw.get("weight", 100.0))
            except Exception:
                w = 100.0
            return [{"criterion": crit, "weight": 100.0 if w <= 0 else float(w)}]

        # ── 인식 불가 → 기본
        return _default()


    # ========== 퍼블릭 엔트리 ==========
    async def grade_and_save(
        self,
        payload: SolveRequestUnion,
        user_id: str,
        group_id: int,
        workbook_id: int,
        problem_id: int,
    ) -> SolveResultDTO:
        ref = await self._get_problem_reference(group_id, workbook_id, problem_id)
        if not ref:
            raise HTTPException(status_code=404, detail="PROBLEM_REFERENCE_NOT_FOUND")

        pb = await self._load_problem(problem_id)

        # ✨ problem_ref의 score(또는 points)를 최대점수로 사용
        max_points = float(
            getattr(ref, "score", None)   # 테이블에 'score'가 있으면 우선
            or getattr(ref, "points", None)  # 없으면 'points' 사용
            or 100.0  # 둘 다 없으면 100점 만점
        )

        identity = _resolve_identity_tag(payload.problemType)
        if identity is None:
            raise HTTPException(status_code=400, detail="UNSUPPORTED_PROBLEM_TYPE")

        ctx: Dict[str, Any] | None = None

        # 문제유형별 채점 + AI 피드백 생성 (max_points 스케일링)
        if identity in ("coding", "debugging"):
            test_cases: List[TestCaseInput] = self._extract_test_cases(pb)  # type: ignore
            requested_mode = getattr(pb, "rating_mode", None)
            language = self._normalize_language(payload.code_language)  # type: ignore

            # ▶ rating_mode: 러너 enum으로 보장
            if identity == "debugging":
                rm_raw = _decide_rating_mode_for_debugging(pb, requested_mode)  # 문자열일 수 있음
                rating_mode = _map_rating_mode(rm_raw)                          # RunnerRatingMode로 변환
            else:
                rating_mode = _decide_rating_mode_for_coding(pb, requested_mode)  # 이미 RunnerRatingMode 반환

            # ▶ 디버깅일 때 base_code 선택(참고: reference_codes는 사용하지 않음)
            selected_base_code: Optional[str] = None
            if identity == "debugging":
                base_list: List[Dict[str, Any]] = cast(List[Dict[str, Any]], getattr(pb, "base_code", []) or [])
                for bc in base_list:
                    if (str(bc.get("language") or "").lower() == language):
                        code_v = bc.get("code")
                        if code_v is not None:
                            selected_base_code = str(code_v)
                        break
                if selected_base_code is None and base_list:
                    code_v = base_list[0].get("code")
                    if code_v is not None:
                        selected_base_code = str(code_v)

            # 런너가 base_code 같은 인자를 지원하는지 확인 후, 지원할 때만 전달
            extra_kwargs = {}
            if identity == "debugging" and selected_base_code:
                for cand in ("base_code", "reference_code", "buggy_code", "original_code"):
                    if SolveService._runner_accepts(self.compiler.run_code, cand):  # ← 클래스에서 호출
                        extra_kwargs[cand] = selected_base_code
                        break

            # 최종 실행 (지원하지 않으면 kwargs는 빈 dict -> 안전)
            try:
                run = self.compiler.run_code(
                    language=language,
                    code=payload.codes,  # type: ignore
                    test_cases=test_cases,
                    rating_mode=rating_mode,
                    **extra_kwargs,
                )
            except TypeError as e:
                run = self.compiler.run_code(
                    language=language,
                    code=payload.codes,  # type: ignore
                    test_cases=test_cases,
                    rating_mode=rating_mode,
                )

            raw_results = _normalize_runner_results(run.get("results", []))

            # =========================
            # ★ 조건 체크 + 점수 분배
            # =========================
            # (A) 문제에서 조건 원본 가져오기 (문서 스키마에 맞춰 필드명 조정)
            problem_conditions_raw = getattr(pb, "problem_condition", []) \
                or getattr(pb, "conditions", []) \
                or []

            rule_checks: List[Dict[str, Any]] = []
            if problem_conditions_raw:
                # 규칙 기반 체크
                rule_checks_objs = ConditionChecker.check_all_conditions(
                    conditions=[
                        ProblemConditionCheck(
                            condition=(c if isinstance(c, str) else (c.get("condition") or c.get("description") or "")),
                            is_required=(True if isinstance(c, str) else bool(c.get("is_required", True))),
                            check_type=("code_analysis" if isinstance(c, str) else str(c.get("check_type", "code_analysis"))),
                            description=(c if isinstance(c, str) else (c.get("description") or c.get("condition") or "")),
                        ) for c in problem_conditions_raw
                    ],
                    code=payload.codes,
                    output=(raw_results[0].get("output") if raw_results else ""),
                    expected_output=(raw_results[0].get("expected_output") if raw_results else ""),
                    execution_time=sum(float(r.get("execution_time") or 0.0) for r in raw_results),
                )
                rule_checks = [rc.model_dump() if hasattr(rc, "model_dump") else rc.__dict__ for rc in rule_checks_objs]

            # (선택) GPT 기반 체크도 병행하려면 아래 블록을 사용, 아니면 통째로 제거
            gpt_checks: List[Dict[str, Any]] = []
            if problem_conditions_raw:
                try:
                    gpt_res = await GPTConditionChecker().check_all_conditions_batch(
                        conditions=[(c if isinstance(c, str) else (c.get("condition") or c.get("description") or "")) for c in problem_conditions_raw],
                        code=payload.codes,
                        language=language,
                        problem_description=(getattr(pb, "description", "") or getattr(pb, "title", "")),
                        problem_conditions_check=[
                            ProblemConditionCheck(
                                condition=(c if isinstance(c, str) else (c.get("condition") or c.get("description") or "")),
                                is_required=(True if isinstance(c, str) else bool(c.get("is_required", True))),
                                check_type="gpt_check",
                                description=(c if isinstance(c, str) else (c.get("description") or c.get("condition") or "")),
                            ) for c in problem_conditions_raw
                        ]
                    )
                    gpt_checks = [rc.model_dump() if hasattr(rc, "model_dump") else rc.__dict__ for rc in gpt_res]
                except Exception:
                    gpt_checks = []

            # (B) 결과 병합 정책: AND (원하면 OR/우선순위로 교체 가능)
            merged: List[Dict[str, Any]] = []
            for i in range(max(len(rule_checks), len(gpt_checks))):
                base = (rule_checks[i] if i < len(rule_checks) else (gpt_checks[i] if i < len(gpt_checks) else {})).copy()
                base.setdefault("condition", i + 1)
                base.setdefault("is_required", True)
                base.setdefault("description", base.get("description") or base.get("condition") or f"Condition {i+1}")
                base.setdefault("check_type", base.get("check_type") or "code_analysis")

                if i < len(rule_checks) and i < len(gpt_checks):
                    p_rule = bool(rule_checks[i].get("passed", False))
                    p_gpt  = bool(gpt_checks[i].get("passed", False))
                    base["passed"] = (p_rule and p_gpt)   # ← 정책
                    fb_r = str(rule_checks[i].get("feedback") or "")
                    fb_g = str(gpt_checks[i].get("feedback") or "")
                    base["feedback"] = (fb_r if base["passed"] else (fb_g or fb_r))
                elif i < len(rule_checks):
                    base["passed"] = bool(rule_checks[i].get("passed", False))
                    base["feedback"] = str(rule_checks[i].get("feedback") or "")
                elif i < len(gpt_checks):
                    base["passed"] = bool(gpt_checks[i].get("passed", False))
                    base["feedback"] = str(gpt_checks[i].get("feedback") or "")

                # 문제 정의에 weight가 있으면 반영
                weight = 1.0
                if i < len(problem_conditions_raw) and isinstance(problem_conditions_raw[i], dict):
                    try:
                        weight = float(problem_conditions_raw[i].get("weight", 1.0))
                    except Exception:
                        weight = 1.0
                base["weight"] = weight
                merged.append(base)

            # (C) 스키마 정규화 + 점수 분배
            cond_items = normalize_condition_checks(merged)

            # 총 배점(조건용): 문제에서 주면 그 값, 없으면 0
            POINTS_FOR_CONDITIONS = float(getattr(pb, "condition_points", 0.0))
            cond_items, cond_earned = distribute_condition_scores(cond_items, POINTS_FOR_CONDITIONS)
            # =========================
            # ★ 조건 체크 + 점수 분배 끝
            # =========================

            # 2) AI 점수/피드백
            ai_res = await self.ai.generate_for_problem_type(
                problem_type=("debugging" if identity == "debugging" else "coding"),
                max_points=max_points,
                problem_description=(getattr(pb, "description", "") or getattr(pb, "title", "")),
                code=payload.codes,                      # 제출 코드
                language=language,
                test_results=raw_results,
                condition_check_results=cond_items,      # ★ 분배된 리스트 그대로 전달
                points_for_conditions=POINTS_FOR_CONDITIONS,
            )

            pct = float(ai_res["percent"])
            earned = float(ai_res["score"])
            ai_fb = ai_res["ai_feedback"]
            graded_by = ai_res["graded_by"]

            # 3) 제출본 저장
            status = "SUCCESS" if all(r.get("status") not in ("ERROR", "TIMEOUT") for r in raw_results) else "ERROR"
            ctx = {
                "code": payload.codes,  # 제출 코드
                "language": language,
                "results": raw_results,  # ← input/expected_output 포함된 표준화 결과
                "execution_time_ms": sum(float(r.get("execution_time") or 0.0) for r in raw_results),
                "memory_usage_bytes": max(int(r.get("memory_usage") or 0) for r in raw_results) if raw_results else 0,
                "status": status,
                "error_message": self._collect_first_error(raw_results),
                "ai_feedback": ai_res["ai_feedback"],
                "condition_check_results": cond_items,
            }
            sub = await self._persist_coding(
                user_id=user_id, ref_id=ref.problem_reference_id, identity=identity, ctx=ctx
            )
            is_correct = pct >= self.PASSING_SCORE_DEFAULT

        elif identity == "multiple_choice":
            mc_payload = cast(MultipleChoiceSolveRequest, payload)

            correct: List[int] = _ensure_int_list(getattr(pb, "correct_answers", []))
            selected: List[int] = _ensure_int_list(getattr(mc_payload, "selected_options", []))

            ai_res = await self.ai.generate_for_problem_type(
                problem_type="multiple_choice",
                max_points=max_points,
                problem_description=(getattr(pb, "description", "") or getattr(pb, "title", "")),
                mc_correct_indices=correct,    
                mc_selected_indices=selected,  
            )
            pct = float(ai_res.get("percent", 0))
            earned = float(ai_res.get("score", 0))
            ai_fb = ai_res.get("ai_feedback")
            graded_by = ai_res.get("graded_by")
            is_correct = pct == 100.0
            sub = await self._persist_multiple_choice(
                user_id=user_id,
                ref_id=ref.problem_reference_id,
                identity=identity,
                selected_indices=selected,
                is_correct=is_correct,
            )

        elif identity == "short_answer":
            sa_payload = cast(ShortAnswerSolveRequest, payload)

            # 문제 스키마에 따라 존재하는 필드 선택
            answers: List[str] = _ensure_str_list(
                getattr(pb, "answers", None) or getattr(pb, "answer_text", None)
            )
            mode: ShortMode = _normalize_short_answer_mode(getattr(pb, "rating_mode", "exact"))

            ai_res = await self.ai.generate_for_problem_type(
                problem_type="short_answer",
                max_points=max_points,
                problem_description=(getattr(pb, "description", "") or getattr(pb, "title", "")),
                short_answer_text=sa_payload.answer_text,  # type: ignore
                short_expected_answers=answers,            # ✅ List[str]
                short_rating_mode=mode,                    # ✅ Literal
            )
            pct = float(ai_res.get("percent", 0))
            earned = float(ai_res.get("score", 0))
            ai_fb = ai_res.get("ai_feedback")
            graded_by = ai_res.get("graded_by")
            is_correct = pct == 100.0
            sub = await self._persist_short_answer(
                user_id=user_id,
                ref_id=ref.problem_reference_id,
                identity=identity,
                answers=sa_payload.answer_text,  # 리스트로 저장하는 구현이면 거기에 맞추기
                is_correct=is_correct,
            )

        else:  # subjective
            rubric: Rubric = self._normalize_rubric(getattr(pb, "grading_criteria", None))
            rubric_payload: Optional[str] = json.dumps(rubric, ensure_ascii=False) if rubric else None

            ai_res = await self.ai.generate_for_problem_type(
                problem_type="subjective",
                max_points=max_points,
                problem_description=(getattr(pb, "description", "") or getattr(pb, "title", "")),
                subjective_text=payload.written_text,  # type: ignore
                rubric=rubric_payload,                 # str | None
            )
            pct = float(ai_res["percent"])
            earned = float(ai_res["score"])
            ai_fb = ai_res["ai_feedback"]
            graded_by = ai_res["graded_by"]
            is_correct = pct >= self.PASSING_SCORE_DEFAULT
            sub = await self._persist_subjective(
                user_id=user_id,
                ref_id=ref.problem_reference_id,
                identity=identity,
                answer_text=payload.written_text,  # type: ignore
                is_correct=is_correct,
            )

        # earned는 generate_for_problem_type에서 이미 max_points 기준으로 산출됨

        prof_fb: str | None = None
        if identity in ("coding", "debugging"):
            ai_fb = (ctx or {}).get("ai_feedback")  # 실행 컨텍스트에 동기 저장

        await self._persist_score(
            submission_id=sub.submission_id,
            score=earned,              # ← 저장 값은 실점
            graded_by=graded_by,
            prof_feedback=prof_fb,
            ai_feedback=ai_fb,
        )

        await self.db.commit()
        await self.db.refresh(sub)

        return SolveResultDTO(
            submission_id=sub.submission_id,
            problem_id=pb.problem_id,
            created_at=sub.created_at,
            is_correct=is_correct,
        )

    # ========== 쿼리 헬퍼 ==========
    async def _get_problem_reference(self, group_id: int, workbook_id: int, problem_id: int) -> Optional[ProblemReference]:
        stmt = (
            select(ProblemReference)
            .where(
                and_(
                    ProblemReference.group_id == group_id,
                    ProblemReference.workbook_id == workbook_id,
                    ProblemReference.problem_id == problem_id,
                    ProblemReference.deleted_at.is_(None),
                )
            )
            .order_by(ProblemReference.created_at.desc(), ProblemReference.problem_reference_id.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _load_problem(self, problem_id: int):
        ProblemPoly = with_polymorphic(Problem, "*")
        stmt = select(ProblemPoly).where(
            and_(ProblemPoly.problem_id == problem_id, ProblemPoly.deleted_at.is_(None))
        )
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        if not row:
            raise HTTPException(status_code=404, detail="PROBLEM_NOT_FOUND")
        return row

    def _normalize_language(self, lang: str) -> str:
        l = (lang or "").strip().lower()
        return {
            "py": "python",
            "python3": "python",
            "py3": "python",
            "node": "javascript",
            "js": "javascript",
            "ts": "typescript",
            "c++": "cpp",
            "c++17": "cpp",
            "c++14": "cpp",
            "cxx": "cpp",
            "golang": "go",
            "c#": "csharp",
            "cs": "csharp",
        }.get(l, l)

    # ========== 퍼시스턴스 ==========
    async def _persist_coding(self, *, user_id: str, ref_id: int, identity: str, ctx: Dict[str, Any]) -> Submission:
        Model = CodingSubmission if identity == "coding" else DebuggingSubmission

        # ctx에서 안전하게 뽑기
        exec_status_str = str(ctx.get("status", "ERROR")).upper()
        try:
            exec_status = ModelExecStatus[exec_status_str]
        except Exception:
            exec_status = ModelExecStatus.ERROR

        # execution_time_ms는 ms 단위로 합계를 넣고, 모델 컬럼이 ms인지 s인지 규약을 정하자.
        # 지금 모델은 Float(명시 없음) → ms로 일관 저장 권장.
        exec_time_ms = float(ctx.get("execution_time_ms") or 0.0)
        mem_bytes = int(ctx.get("memory_usage_bytes") or 0)

        sub = Model(
            user_id=user_id,
            problem_reference_id=ref_id,
            submission_type=identity,
            submission_code_log=[],                         # 로그 없으면 빈 리스트
            submission_code=str(ctx.get("code") or ""),
            submission_language=str(ctx.get("language") or ""),
            execution_status=exec_status,                   # ENUM 매핑
            execution_time=exec_time_ms,                    # ms 합계
            memory_usage=mem_bytes,                         # bytes (최대)
            auto_rating_mode=AutoRatingMode.deactive,       # 프로젝트 정책대로
            auto_rating_criteria=None,
            user_test_case_results=ctx.get("results") or [],# ★ 케이스별 결과(JSONB)
            error_message=ctx.get("error_message"),         # 첫 에러 메시지 or None
        )
        self.db.add(sub)
        await self.db.flush()
        return sub

    async def _persist_multiple_choice(self, *, user_id: str, ref_id: int, identity: str,
                                       selected_indices: List[int], is_correct: bool) -> Submission:
        sub = MultipleChoiceSubmission(
            user_id=user_id,
            problem_reference_id=ref_id,
            submission_type=identity,
            selected_option_indices=selected_indices,
            is_correct=is_correct,
        )
        self.db.add(sub)
        await self.db.flush()
        return sub

    async def _persist_short_answer(self, *, user_id: str, ref_id: int, identity: str,
                                    answers: List[str], is_correct: bool) -> Submission:
        sub = ShortAnswerSubmission(
            user_id=user_id,
            problem_reference_id=ref_id,
            submission_type=identity,
            answer=answers,
            is_correct=is_correct,
        )
        self.db.add(sub)
        await self.db.flush()
        return sub

    async def _persist_subjective(self, *, user_id: str, ref_id: int, identity: str,
                                  answer_text: str, is_correct: bool) -> Submission:
        sub = SubjectiveSubmission(
            user_id=user_id,
            problem_reference_id=ref_id,
            submission_type=identity,
            answer=answer_text,
            is_correct=is_correct,
        )
        self.db.add(sub)
        await self.db.flush()
        return sub

    async def _persist_score(
        self,
        *,
        submission_id: int,
        score: float,
        graded_by: Optional[str],
        prof_feedback: Optional[str] = None,
        ai_feedback: Optional[str] = None,
    ):
        gb = (graded_by or "").strip().lower()
        if gb in {"", "ai", "auto", "auto:testcase", "auto:exact", "auto:rule"}:
            gb_to_store = "AI"
        else:
            gb_to_store = graded_by

        sc = SubmissionScore(
            submission_id=submission_id,
            score=float(score),
            graded_by=gb_to_store,
            prof_feedback=prof_feedback,
            ai_feedback=ai_feedback,
        )
        self.db.add(sc)
        await self.db.flush()
        return sc

    # ========== 기타 유틸 ==========
    def _extract_test_cases(self, pb: CodingProblem) -> List[TestCaseInput]:
        raw = getattr(pb, "test_cases", []) or []
        # test_cases가 문자열(JSON)일 가능성 방어
        if isinstance(raw, str):
            try:
                raw = json.loads(raw) or []
            except Exception:
                raw = []
        out: List[TestCaseInput] = []
        for tc in raw:
            if isinstance(tc, dict):
                inp = str(tc.get("input", ""))
                exp = str(tc.get("expected_output", "")).rstrip("\n")
            else:
                inp = str(getattr(tc, "input", "") or "")
                exp = str(getattr(tc, "expected_output", "") or "").rstrip("\n")
            out.append(TestCaseInput(input=inp, expected_output=exp))
        return out

    @staticmethod
    def _collect_first_error(results: List[Dict[str, Any]]) -> Optional[str]:
        for r in results or []:
            if r.get("error"):
                return str(r.get("error"))
        return None
    @staticmethod
    def _runner_accepts(fn, param_name: str) -> bool:
        try:
            return param_name in inspect.signature(fn).parameters
        except Exception:
            return False


#____________________________________________

from app.submission.schemas import (
    SolveResponseUnionMe,
    CodingSolveResponseMe,
    DebuggingSolveResponseMe,
    MultipleChoiceSolveResponseMe,
    ShortAnswerSolveResponseMe,
    SubjectiveSolveResponseMe,
)

# 내부 매핑: submission_type -> 한글 problemType
TYPE_KOR = {
    "coding": "코딩",
    "debugging": "디버깅",
    "multiple_choice": "객관식",
    "short_answer": "단답형",
    "subjective": "주관식",
}


async def list_solves_me(
    db: AsyncSession,
    *,
    user_id: Optional[str] = None,
    group_id: Optional[int] = None,
    workbook_id: Optional[int] = None,
    problem_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[SolveResponseUnionMe]:
    """
    submissions + 각 서브타입 + problem_reference + problem + group + workbook
    조인하여 SolveResponseUnionMe 리스트 반환
    """
    SubPoly = with_polymorphic(
        Submission,
        [CodingSubmission, DebuggingSubmission, MultipleChoiceSubmission, ShortAnswerSubmission, SubjectiveSubmission],
        flat=True,
    )

    stmt = (
        select(
            SubPoly,
            Problem,
            ProblemReference,
            Group,
            Workbook,
        )
        .join(ProblemReference, ProblemReference.problem_reference_id == SubPoly.problem_reference_id)
        .join(Problem, Problem.problem_id == ProblemReference.problem_id)
        .join(Group, Group.group_id == ProblemReference.group_id)
        .join(Workbook, Workbook.workbook_id == ProblemReference.workbook_id)
        .order_by(SubPoly.submission_id.desc())
        .limit(limit)
        .offset(offset)
    )

    conds = []
    if user_id:
        conds.append(SubPoly.user_id == user_id)
    if group_id:
        conds.append(ProblemReference.group_id == group_id)
    if workbook_id:
        conds.append(ProblemReference.workbook_id == workbook_id)
    if problem_id:
        conds.append(ProblemReference.problem_id == problem_id)

    if conds:
        stmt = stmt.where(and_(*conds))

    res = await db.execute(stmt)
    rows = res.all()

    out: List[SolveResponseUnionMe] = []
    for sub, problem, pref, grp, wb in rows:
        base_kwargs = dict(
            solve_id=sub.submission_id,
            problem_id=problem.problem_id,
            problem_name=getattr(problem, "problem_name", getattr(problem, "title", "")) or "",
            group_id=grp.group_id,
            group_name=getattr(grp, "group_name", getattr(grp, "name", "")) or "",
            workbook_id=wb.workbook_id,
            workbook_name=getattr(wb, "workbook_name", getattr(wb, "name", "")) or "",
            user_id=sub.user_id,
            timestamp=sub.created_at,
            passed=_infer_passed(sub),
        )

        stype = sub.submission_type
        if stype == "coding":
            out.append(
                CodingSolveResponseMe(
                    **base_kwargs,
                    problemType="코딩",
                    code_language=getattr(sub, "submission_language", "") or "",
                    code_len=len(getattr(sub, "submission_code", "") or ""),
                )
            )
        elif stype == "debugging":
            out.append(
                DebuggingSolveResponseMe(
                    **base_kwargs,
                    problemType="디버깅",
                    code_language=getattr(sub, "submission_language", "") or "",
                    code_len=len(getattr(sub, "submission_code", "") or ""),
                )
            )
        elif stype == "multiple_choice":
            out.append(
                MultipleChoiceSolveResponseMe(
                    **base_kwargs,
                    problemType="객관식",
                )
            )
        elif stype == "short_answer":
            out.append(
                ShortAnswerSolveResponseMe(
                    **base_kwargs,
                    problemType="단답형",
                )
            )
        else:  # 'subjective'
            out.append(
                SubjectiveSolveResponseMe(
                    **base_kwargs,
                    problemType="주관식",
                )
            )

    return out


def _infer_passed(sub: Submission) -> bool:
    stype = sub.submission_type
    if stype in ("coding", "debugging"):
        status = getattr(sub, "execution_status", None)
        if not status or str(status).upper() != "SUCCESS":
            return False
        results = getattr(sub, "user_test_case_results", []) or []
        return all(bool(r.get("passed")) for r in results) if isinstance(results, list) else False
    return bool(getattr(sub, "is_correct", False))


#_________________________________________________________________
# POST RUN "/run_code" 엔드포인트용
def _to_runner_mode(value: Optional[str]) -> RunnerRatingMode:
    """
    프론트가 'Hard', 'hard', 'HARD' 등으로 보내도 안전하게 매핑.
    미지정/알 수 없는 값은 NONE.
    """
    if not value:
        return RunnerRatingMode.NONE
    v = str(value).strip().lower()
    return {
        "hard": RunnerRatingMode.HARD,
        "space": RunnerRatingMode.SPACE,
        "regex": RunnerRatingMode.REGEX
    }.get(v, RunnerRatingMode.NONE)


def _to_lang_enum(lang: str) -> languageEnum:
    """
    DB Enum으로 안전 매핑. 모르면 etc로 저장.
    """
    v = (lang or "").strip().lower()
    try:
        return languageEnum(v)
    except Exception:
        return languageEnum.etc


def _normalize_testcases(data: RunCodeRequest) -> List[Dict[str, str]]:
    raw = data.test_cases if data.test_cases else data.testcases
    out: List[Dict[str, str]] = []
    for tc in raw:
        # tc는 TestCase 모델이거나 dict일 수 있음
        _in = getattr(tc, "input", None) if not isinstance(tc, dict) else tc.get("input")
        _ex = getattr(tc, "expected_output", None) if not isinstance(tc, dict) else tc.get("expected_output")
        out.append({"input": _in or "", "expected_output": (_ex or "").rstrip("\n")})
    return out


def _normalize_language_global(lang: str) -> str:
    l = (lang or "").strip().lower()
    return {
        "py": "python",
        "python3": "python",
        "py3": "python",
        "node": "javascript",
        "js": "javascript",
        "ts": "typescript",
        "c++": "cpp",
        "c++17": "cpp",
        "c++14": "cpp",
        "cxx": "cpp",
        "golang": "go",
        "c#": "csharp",
        "cs": "csharp",
    }.get(l, l)

async def run_code_and_log(
    db: AsyncSession,
    body: RunCodeRequest,
    *,
    user_id: str,
    problem_reference_id: int,
) -> RunCodeResponse:
    # 1) 테스트케이스 정규화
    tcs_data = _normalize_testcases(body)
    language = _normalize_language_global(body.language)

    # 2) rating_mode 결정
    has_any_expected = any(bool(tc.get("expected_output")) for tc in tcs_data)
    requested_mode = getattr(body, "rating_mode", None)
    rating_mode = _to_runner_mode(getattr(requested_mode, "value", requested_mode)) if has_any_expected else RunnerRatingMode.NONE

    # 3) 실행
    runner = get_runner()
    test_cases: List[TestCaseInput] = [
        TestCaseInput(input=tc["input"], expected_output=tc["expected_output"]) for tc in tcs_data
    ]
    result = runner.run_code(
        language=language,
        code=body.code,
        test_cases=test_cases,
        rating_mode=rating_mode,
    )

    # 4) 결과 정규화
    # 러너 호출 후
    norm_results = _normalize_runner_results(result.get("results", []))

    # 프론트 응답: 요약형
    resp_results = [TestCaseResult(output=str(r.get("output") or ""), passed=bool(r.get("passed"))) for r in norm_results]
    response = RunCodeResponse(results=resp_results)

    # 로그 저장용 집계
    case_peak_mem = max((int(r.get("memory_usage") or 0) for r in norm_results), default=0)
    total_time_ms = sum(float(r.get("execution_time") or 0.0) for r in norm_results)
    compile_peak = int(result.get("compile_memory_usage") or 0)
    max_mem = max(case_peak_mem, compile_peak)

    error_details = []
    any_error = False
    for r in norm_results:
        st = str(r.get("status") or "").upper()
        if st in ("ERROR", "TIMEOUT") or (r.get("error") not in (None, "")):
            any_error = True
            error_details.append({
                "test_case_index": r.get("test_case_index"),
                "status": st if st else ("ERROR" if r.get("error") else "UNKNOWN"),
                "error": r.get("error") or "",
            })

    # DB 모델 필드명 주의: test_cases_results (복수형 s)
    log = TestcasesExecutionLog(
        user_id=user_id,
        problem_reference_id=problem_reference_id,
        code=body.code,
        language=_to_lang_enum(language),
        test_cases_results=norm_results,   # input/expected_output 포함되어 저장됨
        memory_usage=max_mem,              # bytes
        is_error=any_error,
        running_time=total_time_ms,        # ms
        error_details=error_details,
    )
    db.add(log)
    await db.flush()

    return response

#______________________________________________________________________________________________
async def _resolve_problem_reference_id(
    db: AsyncSession,
    *,
    group_id: int,
    workbook_id: int,
    problem_id: int,
) -> Optional[int]:
    stmt = (
        select(ProblemReference.problem_reference_id)
        .where(
            and_(
                ProblemReference.group_id == group_id,
                ProblemReference.workbook_id == workbook_id,
                ProblemReference.problem_id == problem_id,
                # 필요시: 삭제 플래그가 있으면 제외
                # ProblemReference.is_deleted == False,
            )
        )
        .limit(1)
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none()

async def create_submission_score_crud(
    db: AsyncSession,
    *,
    submission_id: int,
    score: float,
    prof_feedback: str,
    graded_by: Optional[str],
) -> SubmissionScore:
    # 제출 존재 확인
    sub = (await db.execute(
        select(Submission).where(Submission.submission_id == submission_id)
    )).scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="SUBMISSION_NOT_FOUND")

    # ref에서 최대점수 조회
    ref = (await db.execute(
        select(ProblemReference).where(
            ProblemReference.problem_reference_id == sub.problem_reference_id
        )
    )).scalar_one_or_none()

    max_points = float(
        getattr(ref, "score", None) or getattr(ref, "points", None) or 100.0
    )

    if score < 0.0 or score > max_points:
        raise HTTPException(status_code=400, detail=f"SCORE_OUT_OF_RANGE_MAX_{max_points}")

    sc = SubmissionScore(
        submission_id=submission_id,
        score=float(score),            # 수동 입력은 실점 그대로 저장
        prof_feedback=prof_feedback,
        graded_by=graded_by or "PROFESSOR",
    )
    db.add(sc)
    await db.flush()
    return sc

#_____________________________________________________________________________________________________
#get ("/groups/{group_id}/workbooks/{workbook_id}/submissions")
async def list_latest_submission_summaries_crud(
    db: AsyncSession,
    *,
    user_id: str,
    group_id: int,
    workbook_id: int,
    problem_reference_id: Optional[int] = None,   # ← 선택 필터 (기존 problem_id 제거)
) -> List[getAllSubmissionsResponse]:
    """
    특정 user가 특정 group/workbook (선택적으로 특정 problem_reference_id)에 대해
    제출한 기록을 '문제 레퍼런스(ProblemReference)'별로 요약해서 반환.
    - 각 문제 인스턴스별로 첫 제출 시각, 마지막 제출 시각, 마지막 제출의 최신 점수, reviewed 여부
    """

    pr = ProblemReference
    s = Submission
    ss = SubmissionScore

    # 1) 문제 레퍼런스별 min/max submission_id 집계
    base_q = (
        select(
            pr.problem_reference_id.label("problem_reference_id"),
            func.min(s.submission_id).label("min_sid"),
            func.max(s.submission_id).label("max_sid"),
        )
        .join(s, s.problem_reference_id == pr.problem_reference_id)
        .where(
            pr.group_id == group_id,
            pr.workbook_id == workbook_id,
            s.user_id == user_id,
        )
        .group_by(pr.problem_reference_id)
    )

    if problem_reference_id is not None:
        base_q = base_q.where(pr.problem_reference_id == problem_reference_id)

    subq = base_q.subquery()

    # 2) min/max 제출 시각
    min_created_at_sq = (
        select(Submission.created_at)
        .where(Submission.submission_id == subq.c.min_sid)
        .scalar_subquery()
    )
    max_created_at_sq = (
        select(Submission.created_at)
        .where(Submission.submission_id == subq.c.max_sid)
        .scalar_subquery()
    )

    # 3) 마지막 제출(max_sid)에 대한 최신 점수 1건
    score_sq = (
        select(ss.score)
        .where(ss.submission_id == subq.c.max_sid)
        .order_by(ss.created_at.desc(), ss.submission_score_id.desc())
        .limit(1)
        .scalar_subquery()
    )

    # 4) 최종 결과 셀렉트
    final_stmt = select(
        subq.c.max_sid.label("submission_id"),
        literal(user_id).label("user_id"),
        subq.c.problem_reference_id,
        score_sq.label("score"),
        case(
            (score_sq.is_(None), False),
            else_=True,
        ).label("reviewed"),
        min_created_at_sq.label("created_at"),
        max_created_at_sq.label("updated_at"),
    ).order_by(subq.c.problem_reference_id.asc())

    rows = (await db.execute(final_stmt)).all()

    # 5) 응답 매핑
    items: List[getAllSubmissionsResponse] = []
    for r in rows:
        items.append(
            getAllSubmissionsResponse(
                submission_id=r.submission_id,
                user_id=r.user_id,
                # ⬇️ 스키마가 problem_reference_id를 받도록 업데이트되어야 함
                problem_id=r.problem_reference_id,
                score=r.score,
                reviewed=bool(r.reviewed),
                created_at=r.created_at,
                updated_at=r.updated_at,
            )
        )
    return items


async def list_scores_by_submission_id(
    db: AsyncSession,
    submission_id: int,
) -> List[SubmissionGetScoreResponse]:
    """
    특정 submission_id의 채점 이력 목록을 반환.
    """
    stmt = (
        select(SubmissionScore)
        .where(
            SubmissionScore.submission_id == submission_id,
            SubmissionScore.is_deleted.is_(False),
        )
        .order_by(SubmissionScore.created_at.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()

    return [
        SubmissionGetScoreResponse(
            submission_score_id=r.submission_score_id,
            submission_id=r.submission_id,
            score=r.score,
            prof_feedback=r.prof_feedback,
            graded_by=r.graded_by,
            created_at=r.created_at,
        )
        for r in rows
    ]

#______________________________________________________________________________________________
# router.get "/group_id/{group_id}/workbook_id/{workbook_id}/problem_id/{problem_id}"
# 현재 안써요
async def _get_problem_reference(
    db: AsyncSession, *, group_id: int, workbook_id: int, problem_id: int
) -> ProblemReference:
    stmt = select(ProblemReference).where(
        and_(
            ProblemReference.group_id == group_id,
            ProblemReference.workbook_id == workbook_id,
            ProblemReference.problem_id == problem_id,
            ProblemReference.deleted_at.is_(None),
        )
    )
    ref = (await db.execute(stmt)).scalar_one_or_none()
    if not ref:
        raise HTTPException(status_code=404, detail="PROBLEM_REFERENCE_NOT_FOUND")
    return ref


async def _get_latest_submission_for_ref(
    db: AsyncSession, *, user_id: str, problem_reference_id: int
) -> Submission:
    SubPoly = with_polymorphic(
        Submission,
        [CodingSubmission, DebuggingSubmission, MultipleChoiceSubmission, ShortAnswerSubmission, SubjectiveSubmission],
        flat=True,
    )
    stmt = (
        select(SubPoly)
        .where(
            SubPoly.problem_reference_id == problem_reference_id,
            SubPoly.user_id == user_id,
        )
        .order_by(SubPoly.submission_id.desc())
        .limit(1)
    )
    sub = (await db.execute(stmt)).scalar_one_or_none()
    if not sub:
        raise HTTPException(status_code=404, detail="SUBMISSION_NOT_FOUND_FOR_USER")
    return sub


async def _get_problem(db: AsyncSession, *, problem_id: int) -> Problem:
    ProblemPoly = with_polymorphic(Problem, "*")
    stmt = select(ProblemPoly).where(
        and_(ProblemPoly.problem_id == problem_id, ProblemPoly.deleted_at.is_(None))
    )
    row = (await db.execute(stmt)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="PROBLEM_NOT_FOUND")
    return row


async def _get_latest_score_row(db: AsyncSession, *, submission_id: int) -> Optional[SubmissionScore]:
    stmt = (
        select(SubmissionScore)
        .where(SubmissionScore.submission_id == submission_id, SubmissionScore.is_deleted.is_(False))
        .order_by(SubmissionScore.created_at.desc(), SubmissionScore.submission_score_id.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


def _normalize_test_cases_from_problem(pb: Problem) -> List[CodingTestCase]:
    raw = getattr(pb, "test_cases", []) or []
    out: List[CodingTestCase] = []
    if isinstance(raw, str):
        import json
        try:
            raw = json.loads(raw) or []
        except Exception:
            raw = []
    for tc in raw:
        if isinstance(tc, dict):
            _in = str(tc.get("input", "") or "")
            _ex = str(tc.get("expected_output", "") or "").rstrip("\n")
        else:
            _in = str(getattr(tc, "input", "") or "")
            _ex = str(getattr(tc, "expected_output", "") or "").rstrip("\n")
        out.append(CodingTestCase(input=_in, expected_output=_ex))
    return out


def _map_overall_status_for_coding(results: List[Dict[str, Any]], exec_status: Optional[str]) -> OverallStatus:
    # exec_status: "SUCCESS" | "ERROR" 등 (대문자 가정)
    if (exec_status or "").upper() != "SUCCESS":
        return OverallStatus.error

    if not results:
        return OverallStatus.failed

    passed_flags = [bool(r.get("passed")) for r in results]
    if all(passed_flags):
        return OverallStatus.success
    if any(passed_flags):
        return OverallStatus.partial
    return OverallStatus.failed


def _map_overall_status_from_score(passed: bool, score: Optional[float], max_points: Optional[float]) -> OverallStatus:
    if passed:
        return OverallStatus.success
    if score is not None and max_points and 0.0 < float(score) < float(max_points):
        return OverallStatus.partial
    return OverallStatus.failed


def _map_coding_results_to_schema(results: List[Dict[str, Any]]) -> List[CodingTestResult]:
    items: List[CodingTestResult] = []
    for r in results or []:
        items.append(
            CodingTestResult(
                input=str(r.get("input") or ""),
                actual_output=str(r.get("output") or r.get("actual_output") or ""),
                passed=bool(r.get("passed")),
                # 실행시간 필드가 seconds/ms 혼재일 수 있으므로 그대로 전달(프론트에서 단위 라벨링 권장)
                exec_time_ms=float(r.get("exec_time_ms") or r.get("execution_time") or 0.0),
            )
        )
    return items




# -----------------------------
# Public API
# -----------------------------
async def build_submission_detail_payload(
    db: AsyncSession,
    *,
    submission_id: int,
) -> Optional[Dict[str, Any]]:
    """
    submission_id를 받아 예시와 동일한 형태의 payload(dict)를 구성해 반환.
    문제 유형별로 다음 키를 채워준다:

    - 공통: solve_id, problem_id, problem_name, problemType, passed, overall_status, ai_feedback
    - 코딩/디버깅:
        submitted_code, code_language, code_len,
        test_cases[{input, expected_output}],
        test_results[{input, actual_output, passed, time_ms}],
        execution_time, condition_check_results
    - 객관식:
        selected_options, condition_check_results
    - 단답형/주관식:
        submitted_text, condition_check_results
    """
    sub, score_row, pref = await _fetch_bundle(db, submission_id)
    if sub is None:
        return None

    problem_id = getattr(pref, "problem_id", None) or getattr(pref, "id", None) or getattr(pref, "problem_reference_id", None)
    problem_name = _resolve_problem_name(pref)

    # 임시 컨텍스트(JSONB)에서 타입별 데이터 추출 (SolveService에서 저장했다고 가정)
    ctx: Dict[str, Any] = getattr(sub, "temporary_field_json", {}) or {}

    # 최신 점수/피드백
    total_score: float = float(getattr(score_row, "score", 0.0)) if score_row else 0.0
    ai_feedback_raw = getattr(score_row, "ai_feedback", "") if score_row else ""
    ai_feedback = "" if ai_feedback_raw is None or str(ai_feedback_raw).strip().lower() == "null" else str(ai_feedback_raw)

    # 배점 (정답 여부/컷오프 계산에 사용)
    points = _extract_points(pref)

    # 유형 판정
    identity = _resolve_identity_from_submission(sub.submission_type)  # "코딩" | "디버깅" | "객관식" | "단답형" | "주관식"

    # 공통 필드 틀
    base: Dict[str, Any] = {
        "solve_id": int(sub.submission_id),
        "problem_id": int(problem_id) if problem_id is not None else None,
        "problem_name": problem_name,
        "problemType": identity,
        "ai_feedback": ai_feedback,
    }

    # ---------------------------
    # 유형별 분기
    # ---------------------------
    if identity in ("코딩", "디버깅"):
        # 코드/언어
        submitted_code = str(ctx.get("code", "") or "")
        code_language = str(ctx.get("language", "") or "")
        code_len = len(submitted_code)

        # 실행 결과(러너 결과를 표준화)
        raw_results: List[Dict[str, Any]] = _as_list(ctx.get("results"))
        test_results: List[Dict[str, Any]] = []
        for r in raw_results:
            test_results.append({
                "input": r.get("input", ""),
                "actual_output": r.get("output", r.get("actual_output", "")),
                "passed": bool(r.get("passed", False)),
                "time_ms": float(r.get("execution_time", r.get("time_ms", 0.0)) or 0.0),
            })

        # 테스트케이스 추론(있으면 그대로, 없으면 results에서 input/expected_output 추출)
        test_cases: List[Dict[str, Any]] = []
        raw_cases = _as_list(ctx.get("test_cases"))
        if raw_cases:
            for c in raw_cases:
                test_cases.append({
                    "input": c.get("input", ""),
                    "expected_output": c.get("expected_output", ""),
                })
        else:
            # results에 기대출력 포함되어 있을 수도 있음
            for r in raw_results:
                if "expected_output" in r:
                    test_cases.append({
                        "input": r.get("input", ""),
                        "expected_output": r.get("expected_output", ""),
                    })

        # 전체 실행 시간
        execution_time = float(ctx.get("execution_time_ms") or sum(t["time_ms"] for t in test_results) if test_results else 0.0)

        # 조건결과: DB 저장 포맷(ConditionResult 또는 과거 포맷)을 예시 포맷으로 변환
        cond_raw = _as_list(getattr(sub, "condition_check_results", None))
        condition_check_results = [_to_example_condition_ref(x) for x in cond_raw]

        # 통과/상태
        tests_all_passed = (all(tr["passed"] for tr in test_results) if test_results else False)
        cond_required_all_passed = _all_required_conditions_passed(cond_raw)
        passed = bool(tests_all_passed and cond_required_all_passed)
        overall_status = (
            "all_passed" if passed else
            ("success" if tests_all_passed else ("partial_success" if _has_any_pass(cond_raw) else "failed"))
        )

        return {
            **base,
            "passed": passed,
            "overall_status": overall_status,
            "submitted_code": submitted_code,
            "code_language": code_language,
            "code_len": code_len,
            "test_cases": test_cases,
            "test_results": test_results,
            "execution_time": round(execution_time, 3),
            "condition_check_results": condition_check_results,
        }

    elif identity == "객관식":
        # 선택지: SolveService에서 저장한 selected_indices/selected_options 사용
        selected = _as_int_list(ctx.get("selected_options") or ctx.get("selected_indices"))

        # 정답 여부: 점수=만점 or ctx['is_correct']
        is_correct = bool(ctx.get("is_correct")) if "is_correct" in ctx else (total_score >= points if points > 0 else False)

        cond_raw = _as_list(getattr(sub, "condition_check_results", None))
        condition_check_results = [_to_example_condition_ref(x) for x in cond_raw]
        overall_status = (
            "success" if is_correct and _all_required_conditions_passed(cond_raw)
            else ("partial_success" if is_correct or _has_any_pass(cond_raw) else "failed")
        )

        return {
            **base,
            "passed": is_correct,
            "overall_status": overall_status,
            "selected_options": selected,
            "condition_check_results": condition_check_results,
        }

    elif identity == "단답형":
        submitted_text = str(ctx.get("answer_text", ctx.get("submitted_text", "")) or "")

        # 단답형: 보통 100점=정답
        passed = (total_score >= points) if points > 0 else False

        cond_raw = _as_list(getattr(sub, "condition_check_results", None))
        condition_check_results = [_to_example_condition_ref(x) for x in cond_raw]
        overall_status = (
            "success" if passed and _all_required_conditions_passed(cond_raw)
            else ("partial_success" if passed or _has_any_pass(cond_raw) else "failed")
        )

        return {
            **base,
            "passed": passed,
            "overall_status": overall_status,
            "submitted_text": submitted_text,
            "condition_check_results": condition_check_results,
        }

    else:  # "주관식"
        submitted_text = str(ctx.get("written_text", ctx.get("submitted_text", "")) or "")

        # 컷오프(예: 60%) — points 기준으로 환산
        cutoff_pct = float(ctx.get("cutoff_percent", 60.0))
        passed = False
        if points > 0:
            pct = (total_score / points) * 100.0
            passed = pct >= cutoff_pct

        cond_raw = _as_list(getattr(sub, "condition_check_results", None))
        condition_check_results = [_to_example_condition_ref(x) for x in cond_raw]
        overall_status = (
            "success" if passed and _all_required_conditions_passed(cond_raw)
            else ("partial_success" if passed or _has_any_pass(cond_raw) else "failed")
        )

        return {
            **base,
            "passed": passed,
            "overall_status": overall_status,
            "submitted_text": submitted_text,
            "condition_check_results": condition_check_results,
        }


# -----------------------------
# DB fetch helpers
# -----------------------------
async def _fetch_bundle(
    db: AsyncSession,
    submission_id: int
) -> Tuple[Optional[Submission], Optional[SubmissionScore], Optional[ProblemReference]]:
    sub = await db.scalar(
        select(Submission).where(Submission.submission_id == submission_id)
    )
    if sub is None:
        return None, None, None

    score_row = await db.scalar(
        select(SubmissionScore)
        .where(
            SubmissionScore.submission_id == submission_id,
            SubmissionScore.is_deleted == False,  # noqa
        )
        .order_by(desc(SubmissionScore.created_at))
        .limit(1)
    )

    pref = await db.scalar(
        select(ProblemReference).where(
            ProblemReference.problem_reference_id == sub.problem_reference_id
        )
    )
    return sub, score_row, pref


# -----------------------------
# Mapping/Normalize helpers
# -----------------------------
def _resolve_identity_from_submission(submission_type: str) -> str:
    """
    Submission.submission_type → 한글 problemType
    """
    m = {
        "coding": "코딩",
        "debugging": "디버깅",
        "multiple_choice": "객관식",
        "short_answer": "단답형",
        "subjective": "주관식",
    }
    return m.get(str(submission_type).lower(), "코딩")


def _resolve_problem_name(pref: Optional[ProblemReference]) -> Optional[str]:
    if pref is None:
        return None
    for k in ("title", "name", "problem_name"):
        if hasattr(pref, k):
            v = getattr(pref, k)
            if isinstance(v, str) and v.strip():
                return v
    # 혹시 description의 앞부분으로 대체
    desc = getattr(pref, "description", None)
    if isinstance(desc, str) and desc.strip():
        return desc.strip().splitlines()[0][:80]
    return None


def _extract_points(pref: Optional[ProblemReference]) -> float:
    if pref is None:
        return 100.0
    for field in ("score", "points", "max_points"):
        if hasattr(pref, field):
            val = getattr(pref, field)
            try:
                if val is not None:
                    return float(val)
            except Exception:
                pass
    return 100.0


def _as_list(v: Any) -> List[Any]:
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def _as_int_list(v: Any) -> List[int]:
    out: List[int] = []
    for x in _as_list(v):
        try:
            out.append(int(x))
        except Exception:
            continue
    return out


def _to_example_condition_ref(item: Any) -> Dict[str, Any]:
    """
    DB에 저장된 condition_check_results(ConditionResult 포맷 or old 포맷)를
    예시 포맷으로 변환:
    { "condition", "is_required", "check_type", "description", "passed", "feedback" }
    """
    # dict/obj 모두 허용
    g = (lambda k, d=None: (getattr(item, k, d) if not isinstance(item, dict) else item.get(k, d)))

    # status 또는 passed → passed(bool)
    status = g("status")
    passed = bool(g("passed", False))
    if status is not None and not isinstance(passed, bool):
        passed = True if str(status).lower() == "pass" else False

    return {
        "condition": str(g("condition", "")) or str(g("description", "")) or "",
        "is_required": bool(g("is_required", True)),
        "check_type": str(g("check_type", "code_analysis")),
        "description": str(g("description", "")) or str(g("condition", "")) or "",
        "passed": passed,
        "feedback": str(g("feedback", "")) if g("feedback", "") is not None else "",
    }


def _all_required_conditions_passed(cond_raw: List[Any]) -> bool:
    if not cond_raw:
        return True
    for x in cond_raw:
        g = (lambda k, d=None: (getattr(x, k, d) if not isinstance(x, dict) else x.get(k, d)))
        required = bool(g("is_required", True))
        status = g("status")
        passed = bool(g("passed", False))
        if status is not None and not isinstance(passed, bool):
            passed = True if str(status).lower() == "pass" else False
        if required and not passed:
            return False
    return True


def _has_any_pass(cond_raw: List[Any]) -> bool:
    for x in cond_raw:
        g = (lambda k, d=None: (getattr(x, k, d) if not isinstance(x, dict) else x.get(k, d)))
        status = g("status")
        passed = bool(g("passed", False))
        if status is not None and not isinstance(passed, bool):
            passed = True if str(status).lower() == "pass" else False
        if passed:
            return True
    return False
