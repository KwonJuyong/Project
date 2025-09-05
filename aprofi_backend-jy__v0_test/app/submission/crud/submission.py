# app/submission/crud/submission.py
from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
 
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, case, literal
from sqlalchemy.orm import with_polymorphic
from fastapi import HTTPException
from datetime import datetime

from app.submission.schemas import (
    SolveRequestUnion, ProblemTypeKOR,
    CodingSolveRequest, DebuggingSolveRequest,
    MultipleChoiceSolveRequest, ShortAnswerSolveRequest, SubjectiveSolveRequest
)

# 문제/레퍼런스 모델
from app.problem.models.problem import Problem
from app.problem.models.coding_problem import CodingProblem, DebuggingProblem
from app.problem.models.multiple_choice_problem import MultipleChoiceProblem
from app.problem.models.short_answer_problem import ShortAnswerProblem
from app.problem.models.subjective_problem import SubjectiveProblem
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
    OverallStatus,
    ExecutionStatusEnum,  # 러너 Enum (비교/상태 문자열 생성용)
)
from app.submission.services.problem_Normalization import problem_Normalization
from app.submission.services.ai_feedback import AIFeedbackService

from app.submission.models.testcases_excution_log import TestcasesExecutionLog, languageEnum
from app.submission.schemas import RunCodeRequest, RunCodeResponse, TestCaseResult, getAllSubmissionsResponse, SubmissionGetScoreResponse

# ---------- 내부 DTO ----------
@dataclass
class SolveResultDTO:
    submission_id: int
    problem_id: int
    created_at: datetime
    is_correct: bool


# ---------- 유틸 매핑 ----------
KOR_TO_IDENTITY = {
    ProblemTypeKOR.coding: "coding",
    ProblemTypeKOR.debugging: "debugging",
    ProblemTypeKOR.multiple_choice: "multiple_choice",
    ProblemTypeKOR.short_answer: "short_answer",
    ProblemTypeKOR.subjective: "subjective",
}

def _map_rating_mode(m: str | None) -> RunnerRatingMode:
    val = (m or "none").strip().lower()
    return {
        "hard": RunnerRatingMode.HARD,
        "space": RunnerRatingMode.SPACE,
        "regex": RunnerRatingMode.REGEX,
        "none": RunnerRatingMode.NONE,
    }.get(val, RunnerRatingMode.NONE)


class SolveService:
    PASSING_SCORE_DEFAULT = 60.0  # 주관/단답 합격선

    def __init__(self, db: AsyncSession, current_user: dict):
        self.db = db
        self.current_user = current_user
        self.ai = AIFeedbackService()

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

        identity = KOR_TO_IDENTITY.get(payload.problemType)
        if identity is None:
            raise HTTPException(status_code=400, detail="UNSUPPORTED_PROBLEM_TYPE")

        if identity == "coding":
            is_correct, score, earned, ctx = await self._grade_coding(payload, pb)
            graded_by = "auto:testcase"
            sub = await self._persist_coding(user_id=user_id, ref_id=ref.problem_reference_id, identity=identity, ctx=ctx)

        elif identity == "debugging":
            is_correct, score, earned, ctx = await self._grade_debugging(payload, pb)
            graded_by = "auto:testcase"
            sub = await self._persist_coding(user_id=user_id, ref_id=ref.problem_reference_id, identity=identity, ctx=ctx)

        elif identity == "multiple_choice":
            is_correct, score, earned = await self._grade_multiple_choice(payload, pb)
            graded_by = "auto:exact"
            sub = await self._persist_multiple_choice(
                user_id=user_id, ref_id=ref.problem_reference_id,
                identity=identity, selected_indices=payload.selected_options,
                is_correct=is_correct
            )

        elif identity == "short_answer":
            is_correct, score, earned = await self._grade_short_answer(payload, pb)
            graded_by = "auto:rule"
            sub = await self._persist_short_answer(
                user_id=user_id, ref_id=ref.problem_reference_id,
                identity=identity, answers=[payload.answer_text],
                is_correct=is_correct
            )

        elif identity == "subjective":
            is_correct, score, earned = await self._grade_subjective(payload, pb)
            graded_by = "ai"
            sub = await self._persist_subjective(
                user_id=user_id, ref_id=ref.problem_reference_id,
                identity=identity, answer_text=payload.written_text,
                is_correct=is_correct
            )

        else:
            raise HTTPException(status_code=400, detail="UNSUPPORTED_PROBLEM_TYPE")

        # 점수 저장
        await self._persist_score(submission_id=sub.submission_id, score=score, graded_by=graded_by)

        # 커밋 & 리프레시
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
        stmt = select(ProblemReference).where(
            and_(
                ProblemReference.group_id == group_id,
                ProblemReference.workbook_id == workbook_id,
                ProblemReference.problem_id == problem_id,
                ProblemReference.deleted_at.is_(None),
            )
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
    # ========== 채점기 ==========
    async def _grade_coding(self, payload: CodingSolveRequest, pb: CodingProblem) -> Tuple[bool, float, float, Dict[str, Any]]:
        test_cases = self._extract_test_cases(pb)
        rating_mode = _map_rating_mode(getattr(pb, "rating_mode", "none"))
        runner = CodeRunner()
        language = self._normalize_language(payload.code_language)
        result = runner.run_code(
            code=payload.codes,
            language=payload.code_language.lower(),
            test_cases=test_cases,
            rating_mode=rating_mode,
        )

        # 실행 결과 집계
        if not result.get("success", False):
            ctx = {
                "code": payload.codes,
                "language": payload.code_language,
                "results": result.get("results", []) or [],
                "execution_time_ms": 0.0,
                "memory_usage_bytes": 0,
                "status": ExecutionStatusEnum.ERROR.name,
                "error_message": self._collect_first_error(result.get("results", []) or []),
            }
            return False, 0.0, 0.0, ctx

        results = result.get("results", []) or []  # per-test
        total = len(results)
        passed = sum(1 for r in results if r.get("passed"))
        overall = result.get("overall_status")

        avg_time = (sum((r.get("execution_time") or 0.0) for r in results) / max(1, total)) if results else 0.0
        max_mem = max(((r.get("memory_usage") or 0) for r in results), default=0)
        status = (
            ExecutionStatusEnum.SUCCESS.name
            if overall in (OverallStatus.ALL_PASSED, OverallStatus.SOME_FAILED)
            else ExecutionStatusEnum.ERROR.name
        )

        if overall == OverallStatus.ALL_PASSED:
            score = 100.0
            is_correct = True
        else:
            score = (passed / total) * 100 if total > 0 else 0.0
            is_correct = False

        ctx = {
            "code": payload.codes,
            "language": language,
            "results": results,
            "execution_time_ms": avg_time,
            "memory_usage_bytes": max_mem,
            "status": status,
            "error_message": None,
        }
        return is_correct, score, score, ctx

    async def _grade_debugging(self, payload: DebuggingSolveRequest, pb: DebuggingProblem):
        # 디버깅도 동일 로직(필요 시 base_code merge 로직 추가 가능)
        return await self._grade_coding(
            CodingSolveRequest(problemType=ProblemTypeKOR.coding, codes=payload.codes, code_language=payload.code_language),  # type: ignore
            pb
        )

    async def _grade_multiple_choice(self, payload: MultipleChoiceSolveRequest, pb: MultipleChoiceProblem):
        correct_answers: List[int] = getattr(pb, "correct_answers", [])
        is_correct = set(payload.selected_options) == set(correct_answers)
        score = 100.0 if is_correct else 0.0
        return is_correct, score, score

    async def _grade_short_answer(self, payload: ShortAnswerSolveRequest, pb: ShortAnswerProblem):
        answers: List[str] = getattr(pb, "answers", [])
        mode = str(getattr(pb, "rating_mode", "exact")).lower()

        if mode == "none" or not answers:
            return False, 0.0, 0.0

        txt = (payload.answer_text or "").strip()
        normalized_txt = problem_Normalization.normalize_space(txt)

        def exact_ok(ans: str) -> bool:
            return problem_Normalization.compare_hard(normalized_txt, problem_Normalization.normalize_space(ans))

        def partial_ok(ans: str) -> bool:
            a = normalized_txt.lower()
            b = problem_Normalization.normalize_space(ans).lower()
            return (a in b) or (b in a)

        def soft_ok(ans: str) -> bool:
            from difflib import SequenceMatcher
            a = normalized_txt.lower()
            b = problem_Normalization.normalize_space(ans).lower()
            return SequenceMatcher(None, a, b).ratio() >= 0.8

        matcher = {
            "exact": exact_ok,
            "partial": partial_ok,
            "soft": soft_ok
        }.get(mode, exact_ok)

        ok = any(matcher(ans) for ans in answers)
        score = 100.0 if ok else 0.0
        return ok, score, score


    @staticmethod
    def _normalize_rubric(rubric) -> str:
        """
        rubric이 str | list[str] | dict | None 등으로 올 수 있으니
        반드시 사람이 읽을 수 있는 문자열로 변환한다.
        """
        if rubric is None:
            return ""
        if isinstance(rubric, str):
            return rubric.strip()
        if isinstance(rubric, (list, tuple)):
            # 리스트 항목들을 글머리표 형태로 합침
            parts = []
            for i, item in enumerate(rubric, 1):
                parts.append(f"{i}. {str(item).strip()}")
            return "\n".join(parts)
        if isinstance(rubric, dict):
            # 키: 값 형태로 펼치기 (중첩되면 단순 문자열화)
            lines = []
            for k, v in rubric.items():
                lines.append(f"- {k}: {v}")
            return "\n".join(lines)
        # 기타 타입 방어
        return str(rubric).strip()

    async def _grade_subjective(self, payload: SubjectiveSolveRequest, pb: SubjectiveProblem):
        raw_rubric = getattr(pb, "grading_criteria", None)
        rubric = self._normalize_rubric(raw_rubric)
        max_points = float(getattr(pb, "max_points", 100) or 100)
        score = await self.ai.score_subjective(text=payload.written_text, rubric=rubric)
        score = max(0.0, min(100.0, float(score)))
        earned = score if max_points == 100 else (score / 100.0) * max_points
        is_correct = score >= self.PASSING_SCORE_DEFAULT
        return is_correct, score, earned

    # ========== 퍼시스턴스 ==========
    async def _persist_coding(self, *, user_id: str, ref_id: int, identity: str, ctx: Dict[str, Any]) -> Submission:
        # CodingSubmission / DebuggingSubmission 공용
        Model = CodingSubmission if identity == "coding" else DebuggingSubmission

        # 모델 Enum로 변환해서 저장 (러너 Enum 아님)
        exec_status = ModelExecStatus[ctx["status"]]

        sub = Model(
            user_id=user_id,
            problem_reference_id=ref_id,
            submission_type=identity,
            submission_code_log=[],                       # 필요 시 로그 추가
            submission_code=ctx["code"],
            submission_language=ctx["language"],
            execution_status=exec_status,
            execution_time=ctx["execution_time_ms"],      # 평균(ms)
            memory_usage=ctx["memory_usage_bytes"],
            auto_rating_criteria=None,
            sample_test_cases_results=ctx["results"],     # 러너 결과 JSONB
            user_test_case_results=[],                    # 사용자 TC는 없으면 빈 리스트
            error_message=ctx.get("error_message"),
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

    async def _persist_score(self, *, submission_id: int, score: float, graded_by: Optional[str]):
        gb = (graded_by or "").strip().lower()
        if gb in {"", "ai", "auto", "auto:testcase", "auto:exact", "auto:rule"}:
            gb_to_store = "AI"
        else:
            gb_to_store = graded_by  # 수동 채점 등은 그대로

        sc = SubmissionScore(
            submission_id=submission_id,
            score=float(score),
            graded_by=gb_to_store,
        )
        self.db.add(sc)
        await self.db.flush()
        return sc

    # ========== 기타 유틸 ==========
    def _extract_test_cases(self, pb: CodingProblem) -> List[Dict[str, str]]:
        raw = getattr(pb, "test_cases", []) or []
        out: List[Dict[str, str]] = []
        for i, tc in enumerate(raw):
            inp = str(tc.get("input", ""))
            exp = str(tc.get("expected_output", ""))
            out.append({"input": inp, "expected_output": exp})
        return out

    @staticmethod
    def _collect_first_error(results: List[Dict[str, Any]]) -> Optional[str]:
        for r in results or []:
            if r.get("error"):
                return str(r.get("error"))
        return None
    
    
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
    # 다형성으로 서브클래스 컬럼까지 한번에 로딩
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
        # 공통 필드
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

        stype = sub.submission_type  # 'coding' | 'debugging' | ...
        ptype_kor = TYPE_KOR.get(stype, "주관식")

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
        else:  # 'subjective' fallback
            out.append(
                SubjectiveSolveResponseMe(
                    **base_kwargs,
                    problemType="주관식",
                )
            )

    return out


def _infer_passed(sub: Submission) -> bool:
    """
    제출 타입별 통과 여부 추정.
    - 코딩/디버깅: 실행 상태가 SUCCESS 이고, sample_test_cases_results가 모두 passed면 True
    - 객관식/단답형/주관식: 모델에 is_correct가 있다고 가정
    """
    stype = sub.submission_type
    if stype in ("coding", "debugging"):
        status = getattr(sub, "execution_status", None)
        if not status or str(status).upper() != "SUCCESS":
            return False
        results = getattr(sub, "sample_test_cases_results", []) or []
        return all(bool(r.get("passed")) for r in results) if isinstance(results, list) else False

    # 기타 유형은 is_correct 필드가 있을 것으로 가정
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
        "regex": RunnerRatingMode.REGEX,
        "none": RunnerRatingMode.NONE,
    }.get(v, RunnerRatingMode.NONE)


def _to_lang_enum(lang: str) -> languageEnum:
    """
    DB Enum으로 안전 매핑. 모르면 etc로 저장.
    """
    v = (lang or "").strip().lower()
    try:
        return languageEnum(v)  # 정확히 일치하면 그대로
    except Exception:
        return languageEnum.etc


def _normalize_testcases(data: RunCodeRequest) -> List[Dict[str, str]]:
    """
    프론트에서 'test_cases' 혹은 'testcases'로 올 수 있으므로 통합.
    RunCodeRequest에 둘 중 하나만 있어도 동작하도록.
    """
    # dataclass/Model에 없는 필드를 raw dict에서 꺼내는 방어 로직
    # FastAPI가 모델 검증 전에 body를 dict로 넘기면 필요 없지만, 안전하게 처리
    raw = getattr(data, "testcases", None)
    if raw is None and hasattr(data, "test_cases"):
        raw = getattr(data, "test_cases", None)

    raw = raw or []

    norm: List[Dict[str, str]] = []
    for tc in raw:
        # pydantic 모델이든 dict든 모두 대응
        _in = getattr(tc, "input", None) if not isinstance(tc, dict) else tc.get("input")
        _ex = getattr(tc, "expected_output", None) if not isinstance(tc, dict) else tc.get("expected_output")
        norm.append({"input": _in or "", "expected_output": _ex or ""})
    return norm


async def run_code_and_log(
    db: AsyncSession,
    body: RunCodeRequest,
    *,
    user_id: str,
    problem_reference_id: int,
) -> RunCodeResponse:
    """
    - 코드 실행
    - 테스트케이스 판정
    - testcases_execution_logs 테이블에 실행 기록 저장
    - 응답 스키마로 results만 돌려줌
    """
    # 1) 러너 실행
    runner = CodeRunner()
    tcs = _normalize_testcases(body)
    result = runner.run_code(
        code=body.code,
        language=body.language.lower(),
        test_cases=tcs,
        rating_mode=_to_runner_mode(getattr(body, "rating_mode", None)),
    )

    # 러너 결과를 응답 스키마로 변환
    resp_results = [
        TestCaseResult(
            output=str(r.get("output") or ""),
            passed=bool(r.get("passed")),
        )
        for r in (result.get("results") or [])
    ]
    response = RunCodeResponse(results=resp_results)

    # 2) DB 로그 저장
    # 메모리/시간/에러는 간단 집계 (원하면 더 정교하게 바꿔도 됨)
    results_list = (result.get("results") or [])
    max_mem = 0
    total_time = 0.0
    any_error = False
    error_details: List[Dict[str, Any]] = []
    for r in results_list:
        max_mem = max(max_mem, int(r.get("memory_usage") or 0))
        total_time += float(r.get("execution_time") or 0.0)
        if r.get("status") != "SUCCESS" or r.get("error"):
            any_error = True
            error_details.append(
                {
                    "test_case_index": r.get("test_case_index"),
                    "status": r.get("status"),
                    "error": r.get("error"),
                }
            )

    # language Enum 매핑
    lang_enum = _to_lang_enum(body.language)

    log = TestcasesExecutionLog(
        user_id=user_id,
        problem_reference_id=problem_reference_id,
        code=body.code,
        language=lang_enum,
        sample_test_cases_results=results_list,  # 러너 원본 결과를 그대로 저장(필요 시 축약 가능)
        user_test_case_results=[],               # 사용자 커스텀 테스트케이스가 있다면 여기에
        memory_usage=max_mem,
        is_error=any_error,
        running_time=total_time,
        error_details=error_details,
    )
    db.add(log)
    # flush까지 해서 PK를 확보할 필요는 없지만, 문제 없도록 flush
    await db.flush()

    # 3) 커밋은 라우터에서 (트랜잭션 일관성 유지)
    return response

#______________________________________________________________________________________________
async def create_submission_score_crud(
    db: AsyncSession,
    *,
    submission_id: int,
    score: float,
    prof_feedback: str,
    graded_by: Optional[str],
) -> SubmissionScore:
    # 1) 제출 존재 여부 확인
    exists_stmt = select(Submission.submission_id).where(
        Submission.submission_id == submission_id
    )
    exists = (await db.execute(exists_stmt)).scalar_one_or_none()
    if not exists:
        raise HTTPException(status_code=404, detail="SUBMISSION_NOT_FOUND")

    # 2) 점수 범위 검증 (원하면 제거 가능)
    if score < 0.0 or score > 100.0:
        raise HTTPException(status_code=400, detail="SCORE_OUT_OF_RANGE")

    # 3) 레코드 생성
    sc = SubmissionScore(
        submission_id=submission_id,
        score=float(score),
        prof_feedback=prof_feedback,
        graded_by=graded_by or "unknown",
    )
    db.add(sc)
    await db.flush()  # PK 확보

    return sc

#_____________________________________________________________________________________________________
#get ("/groups/{group_id}/workbooks/{workbook_id}/problems/{problem_id}/submissions")
async def list_latest_submission_summaries_crud(
    db: AsyncSession,
    *,
    user_id: str,
    group_id: int,
    workbook_id: int,
    problem_id: Optional[int] = None,
) -> List[getAllSubmissionsResponse]:
    """
    - 특정 user가 특정 group/workbook(그리고 선택적 problem_id)에 대해
      제출한 기록을 문제별로 요약해서 반환.
    - created_at : 그 문제에 대한 가장 이른 제출(= submission_id 최솟값)의 created_at
    - updated_at : 그 문제에 대한 가장 최신 제출(= submission_id 최댓값)의 created_at
    - score      : 최신 제출(max_sid)에 대한 SubmissionScore가 있으면 그 최신 score, 없으면 null
    - reviewed   : score 존재 여부
    """

    # (1) 문제별로 min/max submission_id를 뽑는 서브쿼리
    base_q = (
        select(
            ProblemReference.problem_id.label("problem_id"),
            func.min(Submission.submission_id).label("min_sid"),
            func.max(Submission.submission_id).label("max_sid"),
        )
        .join(
            Submission,
            Submission.problem_reference_id == ProblemReference.problem_reference_id,
        )
        .where(
            ProblemReference.group_id == group_id,
            ProblemReference.workbook_id == workbook_id,
            Submission.user_id == user_id,
        )
        .group_by(ProblemReference.problem_id)
    )

    if problem_id is not None:
        base_q = base_q.where(ProblemReference.problem_id == problem_id)

    subq = base_q.subquery()

    # (2) min/max submission_id에 대응하는 created_at 뽑기 (scalar subquery)
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

    # (3) 최신 제출(max_sid)에 대한 최신 score 1건 (있으면)
    score_sq = (
        select(SubmissionScore.score)
        .where(SubmissionScore.submission_id == subq.c.max_sid)
        .order_by(SubmissionScore.created_at.desc(), SubmissionScore.submission_score_id.desc())
        .limit(1)
        .scalar_subquery()
    )

    # (4) 최종 셀렉트
    final_stmt = select(
        subq.c.max_sid.label("submission_id"),
        literal(user_id).label("user_id"),
        subq.c.problem_id,
        score_sq.label("score"),
        case((score_sq.is_(None), False), else_=True).label("reviewed"),
        min_created_at_sq.label("created_at"),
        max_created_at_sq.label("updated_at"),
    )

    rows = (await db.execute(final_stmt)).all()

    # (5) DTO 매핑
    items: List[getAllSubmissionsResponse] = []
    for r in rows:
        items.append(
            getAllSubmissionsResponse(
                submission_id=r.submission_id,
                user_id=r.user_id,
                problem_id=r.problem_id,
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
    - is_deleted = false 만
    - created_at 오름차순(원하면 desc로 변경 가능)
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
            graded_by=r.graded_by,     # AI 채점이면 None
            created_at=r.created_at,
        )
        for r in rows
    ]