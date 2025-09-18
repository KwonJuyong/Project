# app/services/ai_feedback.py

from __future__ import annotations
import os
import re
import json
from typing import List, Dict, Any, Optional, Literal, Tuple

from dotenv import load_dotenv
from openai import AsyncOpenAI
from openai import RateLimitError, APIError, APITimeoutError

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # 통일된 기본 모델


class AIFeedbackService:
    """
    문제유형별 AI 피드백 + 점수 산출 서비스

    반환 형식(dict) — 하위호환 유지 + 확장:
    {
        "percent": float,                 # 0~100 (백분율)
        "score": float,                   # 0~max_points (스케일링, = total_score에 대응)
        "ai_feedback": str | None,        # 한국어 피드백
        "graded_by": str,                 # coding/debugging: 'auto:testcase', mc/short: 'auto:rule'/'auto:exact', subjective: 'AI'

        # === 추가 필드(옵션): 조건 연동 출력 ===
        "condition_results": [            # DB JSONB(Submission.condition_check_results)에 그대로 넣어도 되는 형태
            {
                "condition_id": int,
                "condition": str,
                "status": "pass" | "fail",
                "description": str,
                "feedback": str,
                "score": float,          # 해당 조건 득점(통과 시만)
            },
            ...
        ],
        "condition_points_earned": float, # 조건으로 획득한 합계(분리 관리 시 참고용)
        "all_status": "success" | "fail", # 모든 필수 조건 통과 여부(필수 여부 정보가 없으면 '모두 pass' 기준)
    }
    """

    def __init__(self, *, api_key: Optional[str] = None, model: Optional[str] = None, timeout: float = 30.0):
        self.client = AsyncOpenAI(api_key=api_key or OPENAI_API_KEY, timeout=timeout)
        self.model = model or OPENAI_MODEL

    # -----------------------------
    # Public: Dispatcher
    # -----------------------------
    async def generate_for_problem_type(
        self,
        *,
        problem_type: Literal["coding", "debugging", "multiple_choice", "short_answer", "subjective"],
        max_points: float,  # ← problem_ref.score / points (최대점수)
        # 공통 컨텍스트
        problem_description: str = "",
        # 코딩/디버깅
        code: str = "",
        language: str = "python",
        test_results: Optional[List[Dict[str, Any]]] = None,
        condition_check_results: Optional[List[Dict[str, Any]]] = None,
        # 조건 점수 옵션(선택)
        points_for_conditions: float = 0.0,           # 조건에 배분할 총 배점(기본 0: 조건 득점 분리/미사용)
        # 객관식
        mc_correct_indices: Optional[List[int]] = None,
        mc_selected_indices: Optional[List[int]] = None,
        # 단답형
        short_answer_text: Optional[str] = None,
        short_expected_answers: Optional[List[str]] = None,
        short_rating_mode: Literal["exact", "partial", "soft"] = "exact",
        # 주관식
        subjective_text: Optional[str] = None,
        rubric: Optional[str] = None,
    ) -> Dict[str, Any]:

        condition_check_results = condition_check_results or []

        # 1) 유형별 백분율 및 AI 피드백 산출
        if problem_type in ("coding", "debugging"):
            percent = self._success_rate(test_results or [])
            ai_fb = await self._gen_feedback_coding_like(
                problem_description=problem_description,
                code=code,
                language=language,
                test_results=test_results or [],
                condition_check_results=condition_check_results,
                mode=("debugging" if problem_type == "debugging" else "coding"),
            )
            graded_by = "auto:testcase"

        elif problem_type == "multiple_choice":
            percent, exact = self._score_multiple_choice(
                correct=mc_correct_indices or [],
                selected=mc_selected_indices or [],
            )
            ai_fb = await self._gen_feedback_multiple_choice(
                problem_description=problem_description,
                correct=mc_correct_indices or [],
                selected=mc_selected_indices or [],
                exact_match=exact,
                percent=percent,
            )
            graded_by = "auto:exact"

        elif problem_type == "short_answer":
            # 입력 강제 정규화 (리스트/딕셔너리도 안전)
            student_text_norm = self._normalize(short_answer_text)
            expected_list = short_expected_answers or []
            if not isinstance(expected_list, list):
                expected_list = [expected_list]
            expected_list = [self._normalize(x) for x in expected_list if self._normalize(x)]

            percent = self._score_short_answer(
                student_text=student_text_norm,
                expected=expected_list,
                mode=short_rating_mode,
            )
            ai_fb = await self._gen_feedback_short_answer(
                problem_description=problem_description,
                student_text=student_text_norm,
                expected=expected_list,
                mode=short_rating_mode,
                percent=percent,
            )
            graded_by = "auto:rule"

        else:  # subjective
            percent = await self._score_subjective_llm(subjective_text or "", rubric or "")
            ai_fb = await self._gen_feedback_subjective(
                problem_description=problem_description,
                text=subjective_text or "",
                rubric=rubric or "",
                percent=percent,
            )
            graded_by = "AI"

        # 2) 스케일링: 0~100 → 0~max_points  (=> total_score에 해당)
        score = round((float(percent) / 100.0) * float(max_points), 2)

        # 3) 조건 결과(list[dict]) 기반 합계 점수/전체 통과 여부 계산
        cond_results = condition_check_results or []

        # 조건별 점수 합계 (사전에 분배된 score 필드를 합산)
        cond_sum = round(sum(float(it.get("score", 0.0)) for it in cond_results), 2)

        # 필수 조건(is_required=True) 중 하나라도 실패하면 fail
        all_required_ok = all(
            (not bool(it.get("is_required", True))) or bool(it.get("passed", False))
            for it in cond_results
        )

        return {
            "percent": float(percent),
            "score": score,
            "ai_feedback": ai_fb,
            "graded_by": graded_by,
            "condition_results": cond_results,              # 그대로 저장/반환
            "condition_points_earned": cond_sum,           # 조건 점수 합계
            "all_status": "success" if all_required_ok else "fail",
            # "condition_overall_feedback" 제거 (요약 딕셔너리 사용 안 함)
        }

    # -----------------------------
    # Coding / Debugging
    # -----------------------------
    def _success_rate(self, test_results: List[Dict[str, Any]]) -> float:
        if not test_results:
            return 0.0
        total = len(test_results)
        passed = sum(1 for r in test_results if bool(r.get("passed")))
        return (passed / total) * 100.0

    async def _gen_feedback_coding_like(
        self,
        *,
        problem_description: str,
        code: str,
        language: str,
        test_results: List[Dict[str, Any]],
        condition_check_results: List[Dict[str, Any]],
        mode: Literal["coding", "debugging"] = "coding",
    ) -> str:
        failed: List[Dict[str, Any]] = []
        for idx, r in enumerate(test_results):
            if not r.get("passed"):
                failed.append({
                    "index": idx,
                    "input": r.get("input"),
                    "expected_output": r.get("expected_output"),
                    "output": r.get("output"),
                    "status": r.get("status"),
                    "error": r.get("error"),
                })
        failed = failed[:5]

        system = (
            "당신은 프로그래밍 과제 피드백 코치입니다.\n"
            "- 출력: 한국어 불릿 3~5줄, 과도한 장황함 금지\n"
            "- 포함: (1)실패 원인 추정 (2)구체적 수정 지시(조건/인덱스/슬라이스/포맷/트리밍 등)\n"
            "- 이어서 1~3줄 규모의 ```diff``` 미니 패치 제시(필요시)\n"
            "- 마지막 줄은 엣지케이스(빈/대형 입력, 중복/정렬, 경계값, 타입/오버플로우) 점검 권고\n"
            "- 점수/JSON/전체 해답 금지, 최소 변경만 제시"
        )
        user_ctx = {
            "mode": mode,
            "problem": (problem_description or "")[:2000],
            "language": language,
            "failed_tests": failed,
            "condition_checks": condition_check_results[:10],
            "code_excerpt": (code[:1600] + "...(truncated)") if len(code) > 1600 else code,
        }
        user = (
            "아래 컨텍스트를 바탕으로 피드백을 작성하세요.\n\n"
            f"{json.dumps(user_ctx, ensure_ascii=False)}"
        )
        return await self._chat_once(system, user, max_tokens=500, temperature=0.4, fallback=self._fallback_coding_like(failed))

    def _fallback_coding_like(self, failed: List[Dict[str, Any]]) -> str:
        if failed:
            ids = ", ".join(str(f.get("index")) for f in failed if f.get("index") is not None)
            line1 = f"- 실패 테스트 {len(failed)}건: 케이스 {ids} 입출력 포맷/개행/공백/트리밍 점검."
        else:
            line1 = "- 실패 테스트 요약 없음: 표준입출력 포맷/개행/공백/트리밍 우선 점검."
        return "\n".join([
            line1,
            "- 수정 지시: 비교 연산자/루프 상한/슬라이스/인덱스 범위/초기화/리턴을 문제 정의와 일치.",
            "- 미니 패치 예: ```diff\n- if (i <= n)\n+ if (i < n)\n```",
            "- 엣지: 빈/대형 입력, 중복/정렬, 경계값, 타입 캐스팅/오버플로우 확인."
        ])

    # -----------------------------
    # Multiple Choice
    # -----------------------------
    def _score_multiple_choice(self, *, correct: List[int], selected: List[int]) -> Tuple[float, bool]:
        c_set, s_set = set(correct), set(selected)
        exact = (c_set == s_set)
        if not correct:
            return 0.0, False
        return (100.0 if exact else 0.0), exact

    async def _gen_feedback_multiple_choice(
        self,
        *,
        problem_description: str,
        correct: List[int],
        selected: List[int],
        exact_match: bool,
        percent: float,
    ) -> str:
        sys = "당신은 친근하고 격려적인 프로그래밍 교육 멘토입니다."
        user = f"""
문제 설명:
{(problem_description or '')[:1200]}

학생의 선택: {selected}
정답 개수: {len(correct)}
채점 결과: {percent:.1f}% ({'정확히 일치' if exact_match else '불일치'})

요청:
- 지나친 정답 누설 없이, 선택 전략/오답 유형/지문 해석 팁을 3~4줄로 제시
- 긍정적인 부분 1줄 + 개선 제안 2줄 중심
- 한국어, 이모지 1~2개 허용
"""
        return await self._chat_once(sys, user, max_tokens=300, temperature=0.6, fallback=self._fallback_mc(percent))

    def _fallback_mc(self, percent: float) -> str:
        if percent >= 100:
            return "🎉 정확하게 선택했어요! 풀이 과정을 스스로 설명해보면 더 탄탄해져요."
        return "❌ 정답과 불일치했어요. 지문에서 핵심 키워드와 배제 근거를 먼저 표식한 뒤, 남은 보기의 차이를 비교해 보세요."

    # -----------------------------
    # Short Answer
    # -----------------------------
    def _score_short_answer(self, *, student_text: str, expected: List[str], mode: str) -> float:
        s = self._normalize(student_text)
        if not expected:
            return 0.0
        def exact_ok(ans: str) -> bool:
            return s == self._normalize(ans)
        def partial_ok(ans: str) -> bool:
            a, b = s.lower(), self._normalize(ans).lower()
            return (a in b) or (b in a)
        def soft_ok(ans: str) -> bool:
            import difflib
            a, b = s.lower(), self._normalize(ans).lower()
            return difflib.SequenceMatcher(None, a, b).ratio() >= 0.8
        matcher = {"exact": exact_ok, "partial": partial_ok, "soft": soft_ok}.get(mode, exact_ok)
        ok = any(matcher(ans) for ans in expected)
        return 100.0 if ok else 0.0

    async def _gen_feedback_short_answer(
        self,
        *,
        problem_description: str,
        student_text: str,
        expected: List[str],
        mode: str,
        percent: float,
    ) -> str:
        sys = "당신은 간결성과 정확성을 중시하는 평가자입니다."
        expected_hint = expected[0] if expected else ""
        student_view = self._normalize(student_text)  # 여기서 정규화

        user = f"""
    문제:
    {(problem_description or '')[:1200]}

    학생 답안: {student_view or '(빈 입력)'}
    채점 모드: {mode}
    결과: {percent:.1f}%

    요청:
    - 3~4줄: (1)핵심 개념 일치/불일치 (2)표현의 모호성/단위/포맷 (3)추가 확인 포인트
    - 정답 전체를 그대로 노출하지 말고, 대표 정답 형태만 힌트 수준으로 언급
    - 한국어, 이모지 1개 이하
    힌트 예시(대표): {expected_hint}
    """
        return await self._chat_once(sys, user, max_tokens=280, temperature=0.5, fallback=self._fallback_short(percent))

    def _fallback_short(self, percent: float) -> str:
        return "👍 핵심 용어와 포맷을 다시 한 번 정돈해 보세요. 단위/철자/공백을 정확히 맞추면 정답에 더 가까워집니다." if percent < 100 else "🎉 정확합니다! 같은 개념을 다른 표현으로도 설명해 보세요."

    # -----------------------------
    # Subjective (Essay)
    # -----------------------------
    async def _score_subjective_llm(self, text: str, rubric: str) -> float:
        if not text.strip():
            return 0.0

        try:
            resp = await self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": self._system_prompt_subjective(rubric)},
                    {"role": "user", "content": f"Answer:\n{text.strip()[:6000]}"},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "subjective_score",
                        "schema": {
                            "type": "object",
                            "properties": {"score": {"type": "number", "minimum": 0, "maximum": 100}},
                            "required": ["score"],
                            "additionalProperties": False,
                        },
                        "strict": True,
                    },
                },
                max_output_tokens=40,
            )
            val = None
            if hasattr(resp, "output_parsed") and resp.output_parsed:
                val = resp.output_parsed
            elif hasattr(resp, "output") and resp.output:
                for it in resp.output:
                    if getattr(it, "type", "") == "parsed_json":
                        val = getattr(it, "parsed", None)
                        break
            if isinstance(val, dict) and "score" in val:
                return float(max(0.0, min(100.0, float(val["score"]))))

            text_out = getattr(resp, "output_text", None) or str(resp)
            return self._parse_first_number(text_out)

        except Exception:
            pass

        try:
            prompt = (
                "다음 답안을 0~100으로 채점하세요. 반드시 다음 JSON만 출력: "
                '{"score": <0~100 숫자>}\n\n'
                f"[루브릭]\n{rubric or '일반 원칙 적용'}\n\n[답안]\n{text.strip()[:6000]}"
            )
            cc = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=40,
            )
            content = cc.choices[0].message.content or ""
            return self._parse_first_number(content)
        except Exception:
            return 0.0

    async def _gen_feedback_subjective(self, *, problem_description: str, text: str, rubric: str, percent: float) -> str:
        sys = "당신은 공정하고 엄격하지만 학생을 존중하는 에세이 평가자입니다."
        user = f"""
문제/주제:
{(problem_description or '')[:1200]}

루브릭:
{rubric or '일반 원칙 적용'}

학생 답안(요약 평가):
{text.strip()[:2000]}

점수(백분율): {percent:.1f}%

요청:
- 4~5줄: (1)핵심 주장/근거 평가 (2)논리 전개/구조 (3)사실성·근거성 (4)개선 제안
- 과도한 아부/공허한 칭찬 금지, 구체적 문장으로
"""
        return await self._chat_once(sys, user, max_tokens=360, temperature=0.4, fallback=self._fallback_subjective(percent))

    def _system_prompt_subjective(self, rubric: str) -> str:
        return (
            "You are a strict but fair grader. Return ONLY JSON per schema with a single numeric field 'score' (0~100). "
            "No explanations."
            f"\nRubric:\n{rubric or 'Use general principles.'}"
        )

    def _fallback_subjective(self, percent: float) -> str:
        if percent >= 90:
            return "핵심 주장과 근거가 뚜렷합니다. 결론부에서 함의를 한 줄 더 확장하면 완성도가 높아집니다."
        if percent >= 70:
            return "주장의 방향은 맞지만 근거가 얕습니다. 구체 사례/데이터를 1~2개 보강해 보세요."
        return "핵심 논지를 한 줄로 정리하고, 그에 맞는 근거→분석→결론의 구조를 간결하게 재배치해 보세요."

    # -----------------------------
    # Low-level chat helper
    # -----------------------------
    async def _chat_once(self, system: str, user: str, *, max_tokens: int, temperature: float, fallback: str) -> str:
        try:
            resp = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return (resp.choices[0].message.content or "").strip()
        except (RateLimitError, APITimeoutError, APIError, Exception):
            return fallback

    # -----------------------------
    # Formatting helpers (재사용/디버깅용)
    # -----------------------------
    def _format_test_results(self, test_results: List[Dict[str, Any]]) -> str:
        if not test_results:
            return "테스트 결과 없음"
        passed_count = sum(1 for r in test_results if r.get("passed"))
        total_count = len(test_results)
        lines = [f"총 {total_count}개 테스트 중 {passed_count}개 통과 ({passed_count/total_count*100:.1f}%)", ""]
        for i, r in enumerate(test_results, 1):
            status = "✅ 통과" if r.get("passed") else "❌ 실패"
            lines.append(f"테스트 {i}: {status}")
            if not r.get("passed"):
                lines.append(f"  - 입력: {r.get('input', 'N/A')}")
                lines.append(f"  - 예상: {r.get('expected_output', 'N/A')}")
                lines.append(f"  - 실제: {r.get('output', 'N/A')}")
                if r.get("error"):
                    lines.append(f"  - 오류: {r.get('error')}")
            lines.append("")
        return "\n".join(lines)

    def _format_condition_results(self, condition_results: List[Dict[str, Any]]) -> str:
        if not condition_results:
            return "조건 체크 결과 없음"
        out = [f"총 {len(condition_results)}개 조건 체크", ""]
        for c in condition_results:
            status = "✅ 충족" if c.get("status") == "pass" or c.get("passed") else "❌ 미충족"
            conf = f"({c.get('confidence', 0):.1f})" if c.get("confidence") else ""
            name = c.get("condition") or c.get("description") or "Unknown"
            fb = c.get("feedback", "No feedback")
            out.append(f"{name}: {status} {conf}")
            out.append(f"  - 피드백: {fb}")
            out.append("")
        return "\n".join(out)

    # -----------------------------
    # Condition helpers
    # -----------------------------
    def _distribute_points(self, n: int, total: float) -> List[float]:
        if n <= 0:
            return []
        per = round(total / n, 2)
        scores = [per] * (n - 1)
        tail = round(total - sum(scores), 2)
        scores.append(tail)
        return scores

    def _build_condition_results(
        self,
        *,
        checks: List[Dict[str, Any]] | List[object],
        total_points_for_conditions: float = 0.0,
    ) -> Tuple[List[Dict[str, Any]], float, Literal["success", "fail"]]:
        """
        다양한 형태(checks[i].passed / checks[i]['passed'] …)를 흡수하여
        ConditionResult JSON 리스트, 조건 득점 합계, 전체 통과 여부를 반환.
        필수여부(is_required)가 주어지지 않으면 모두 필수로 간주.
        """
        checks = checks or []
        count = len(checks)
        per_scores = self._distribute_points(count, float(total_points_for_conditions)) if count else []
        results: List[Dict[str, Any]] = []
        earned_sum = 0.0
        passed_all_required = True

        for i, c in enumerate(checks, 1):
            # 속성/키를 모두 허용
            get = (lambda k, d=None: (getattr(c, k, d) if not isinstance(c, dict) else c.get(k, d)))
            passed = bool(get("passed", False))
            condition_text = str(get("condition", "")) or str(get("description", "")) or ""
            description = str(get("description", "")) or condition_text
            feedback = str(get("feedback", "")) if get("feedback", "") is not None else ""
            is_required = bool(get("is_required", True))  # 정보 없으면 필수로 간주

            per = float(per_scores[i - 1]) if i - 1 < len(per_scores) else 0.0
            got = per if passed else 0.0
            earned_sum += got

            if is_required and not passed:
                passed_all_required = False

            results.append({
                "condition_id": i,
                "condition": condition_text,
                "status": "pass" if passed else "fail",
                "description": description,
                "feedback": feedback,
                "score": round(got, 2),
            })

        all_status: Literal["success", "fail"] = "success" if (passed_all_required if results else True) else "fail"
        return results, round(earned_sum, 2), all_status

    # -----------------------------
    # Utils
    # -----------------------------
    def _normalize(self, s: object) -> str:
        if s is None:
            return ""
        if isinstance(s, (list, tuple, set)):
            try:
                s = " ".join(map(str, s))
            except Exception:
                s = " ".join([str(x) for x in list(s)])
        elif isinstance(s, dict):
            try:
                s = json.dumps(s, ensure_ascii=False, separators=(",", ":"))
            except Exception:
                s = str(s)
        elif not isinstance(s, str):
            s = str(s)
        s = s.strip()
        s = re.sub(r"\s+", " ", s)
        return s

    def _parse_first_number(self, s: str) -> float:
        if not s:
            return 0.0
        m = re.search(r"(\d+(?:\.\d+)?)", s)
        if not m:
            return 0.0
        v = float(m.group(1))
        return max(0.0, min(100.0, v))
