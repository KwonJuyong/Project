# app/services/ai_feedback.py
"""
AIFeedbackService
- 목적: 주관식/서술형 등의 답변을 LLM으로 채점(0~100) 점수화
- 핵심 설계 포인트:
  1) **안전성**: 타임아웃, 재시도(지수 백오프), 회로 차단(circuit breaker)
  2) **일관성**: 구조화 출력(가능하면 JSON Schema/structured outputs)로 "숫자만" 받기
  3) **비용/성능**: 모델/토큰 상한, 간단한 캐시(질문+루브릭 해시 키)
  4) **비동기**: FastAPI/AsyncSession 환경에 맞춰 async 클라이언트 사용
  5) **대체 가능성**: OpenAI/Azure OpenAI 모두 쉽게 스위칭 가능

참고:
- Responses API Quickstart/레퍼런스 (공식)  :contentReference[oaicite:1]{index=1}
- Structured Outputs(구조화 출력) 안내 (공식)  :contentReference[oaicite:2]{index=2}
- 레이트 리밋/재시도 베스트 프랙티스 (공식 Cookbook)  :contentReference[oaicite:3]{index=3}
"""

from __future__ import annotations
from typing import Optional, Dict, Any
import asyncio
import hashlib
import json
import os
import time
from dataclasses import dataclass

from pydantic import BaseModel, Field, ValidationError

# --- OpenAI Python SDK (v1) ---
# pip install openai>=1.0.0 httpx
from openai import AsyncOpenAI, RateLimitError, APITimeoutError, APIError  # 공식 SDK  :contentReference[oaicite:4]{index=4}

# =========================
# 1) 공용 설정/모델
# =========================

@dataclass(frozen=True)
class AIFeedbackConfig:
    model: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # 경량/저비용 기본값
    # timeout은 **초 단위**. 짧게 잡으면 빈번한 타임아웃 발생 가능 (공식 가이드 참조)  :contentReference[oaicite:5]{index=5}
    request_timeout: float = float(os.getenv("OPENAI_TIMEOUT", "30"))
    max_retries: int = int(os.getenv("OPENAI_MAX_RETRIES", "3"))
    # 토큰 상한. 모델별 컨텍스트 제한 고려 (ex. 4o-mini 128k 등) → 과도한 프롬프트 방지
    max_input_chars: int = int(os.getenv("AI_MAX_INPUT_CHARS", "8000"))
    # 최소/최대 스코어 클램프
    min_score: float = 0.0
    max_score: float = 100.0
    # 간단 캐시 사용 여부
    enable_cache: bool = True

class SubjectiveScore(BaseModel):
    """구조화 출력 대상(스키마) — 숫자만 강제."""
    score: float = Field(ge=0, le=100, description="0~100 사이 점수")

# =========================
# 2) 본체 클래스
# =========================

class AIFeedbackService:
    """
    ▶ 어떤 부분을 고치면 어떻게 동작이 바뀌는가?
    - 모델 바꾸기: .config.model 값을 "o4-mini" 등으로 교체 → 품질/비용/속도 트레이드오프 변동
    - 타임아웃 조절: .config.request_timeout 조절 → 느린 응답 잘라내기 vs 안정성
    - 재시도 정책: _retryable 호출부 (지수 백오프 로직) 변경 → 레이트리밋/일시 오류 대응 강도
    - 구조화 출력 해제: _call_llm_json_schema 대신 _call_llm_text 사용 → 단순 텍스트 파싱(권장X)
    - 캐시 끄기: enable_cache=False → 매 호출 비용 증가(정밀도↑) / 비용·지연↑
    """

    def __init__(self, client: Optional[AsyncOpenAI] = None, config: Optional[AIFeedbackConfig] = None):
        self.config = config or AIFeedbackConfig()
        # Async 클라이언트: 전역 타임아웃/재시도 정책 일부는 SDK 옵션/코드로 함께 처리
        self.client = client or AsyncOpenAI(timeout=self.config.request_timeout)

        # 매우 단순한 메모리 캐시 (프로덕션: Redis 권장)
        self._cache: Dict[str, float] = {}
        # 회로 차단기 변수
        self._circuit_open_until: float = 0.0

    # =========================
    # 3) 퍼블릭 메서드
    # =========================

    async def score_subjective(self, text: str, rubric: Optional[str]) -> float:
        """
        주관식/서술형 응답을 0~100 점수로 수치화.
        - 입력이 너무 길면 앞부분만 사용(비용/속도 관리)
        - 우선 구조화 출력(JSON Schema)로 점수를 **정확히** 받음
        - 실패/오류 시 폴백: 간단 휴리스틱(길이 기반) → 서비스 연속성 보장

        변경 포인트:
        - rubric을 프롬프트에 **강하게** 반영하려면 system 지침에 루브릭 항목을 bullet로 늘려줘.
        - 프롬프트를 한국어/영어 중 택일하도록 바꾸면 결과 안정성이 달라질 수 있음.
        """
        # 0) 회로 차단: 최근 연속 오류가 있으면 일정 시간 대기
        if time.time() < self._circuit_open_until:
            return self._fallback_length_score(text)

        clean_text = self._prepare_text(text)
        rubric = (rubric or "").strip()
        cache_key = self._make_cache_key(clean_text, rubric)

        if self.config.enable_cache and cache_key in self._cache:
            return self._cache[cache_key]

        # 1) LLM 호출(구조화 출력)
        try:
            score = await self._retryable(self._call_llm_json_schema, clean_text, rubric)
        except Exception:
            # 2) 폴백(휴리스틱): 서비스 중단 방지
            score = self._fallback_length_score(clean_text)
            # 회로 열기: 짧게는 10초(레이트 리밋/네트워크 이슈 때 과도 호출 억제)
            self._circuit_open_until = time.time() + 10

        # 3) 사후 처리(클램프 + 캐시)
        score = float(max(self.config.min_score, min(self.config.max_score, score)))
        if self.config.enable_cache:
            self._cache[cache_key] = score
        return score

    # =========================
    # 4) 내부 유틸
    # =========================

    def _prepare_text(self, text: str) -> str:
        """입력 길이 제한/전처리 — 비용 방어막"""
        t = (text or "").strip()
        if len(t) > self.config.max_input_chars:
            # 너무 긴 입력은 앞부분만 — 필요하면 요약 단계를 추가 가능
            return t[: self.config.max_input_chars]
        return t

    def _make_cache_key(self, text: str, rubric: str) -> str:
        raw = json.dumps({"t": text, "r": rubric, "m": self.config.model}, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def _retryable(self, func, *args, **kwargs):
        """
        재시도(지수 백오프 + Jitter)
        - 레이트 리밋/네트워크 순간 장애에 유효 (공식 권장)  :contentReference[oaicite:6]{index=6}
        """
        delay = 0.8
        for i in range(self.config.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except (RateLimitError, APITimeoutError, APIError) as e:
                if i == self.config.max_retries:
                    raise
                # 점진적으로 대기 증가 + 약간의 랜덤 지터
                jitter = 0.2 * (i + 1)
                await asyncio.sleep(delay + jitter)
                delay *= 2

    def _fallback_length_score(self, text: str) -> float:
        """
        폴백 점수: 입력 길이에 기반한 더미 로직.
        - 장점: 외부 API 장애 시에도 서비스 유지
        - 단점: 실제 품질 보장X → 프로덕션에서는 모니터링으로 발동 빈도 체크
        """
        length = max(1, len((text or "").strip()))
        base = 50 + min(50, length / 4)  # 50~100
        return float(base)

    # =========================
    # 5) LLM 호출 (구조화 출력 경로)
    # =========================

    async def _call_llm_json_schema(self, text: str, rubric: str) -> float:
        """
        Responses API + Structured Outputs로 'score: number'만 받기.
        - 장점: 파싱 오류를 근본적으로 차단 (스키마를 강제)  :contentReference[oaicite:7]{index=7}
        - 구현: SDK의 responses.create() 사용 (모델은 config.model)
        """
        system_prompt = (
            "You are a strict grader. Return ONLY a numeric score in JSON under key 'score', "
            "where 0=worst and 100=best. Consider the rubric carefully.\n\n"
            "Rubric:\n"
            f"{rubric or 'No rubric provided'}"
        )
        user_prompt = (
            "Evaluate the following answer and produce a score 0-100:\n\n"
            f"Answer:\n{text}"
        )

        # (공식 문서의 Responses API 사용 예를 기반으로 구성)  :contentReference[oaicite:8]{index=8}
        # 구조화 출력은 'structured outputs' 기능을 지원하는 모델/엔드포인트에서 최적.  :contentReference[oaicite:9]{index=9}
        resp = await self.client.responses.create(
            model=self.config.model,
            reasoning={"effort": "medium"},  # o3/o4-mini 등 reasoning 옵션 예시 (모델에 따라 무시될 수 있음) :contentReference[oaicite:10]{index=10}
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            # JSON 스키마 강제: Structured Outputs
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
            # 비용/속도 관리: 토큰 상한 설정(모델 컨텍스트 내에서 합리적 수치로)
            max_output_tokens=40,
        )

        # Responses API 결과에서 JSON 추출
        # SDK는 응답 내 다양한 출력 채널을 제공 — 여기선 structured JSON 을 가정
        # (모델/엔드포인트에 따라 resp.output_json, resp.output[0].content[0].text 등 형태가 다를 수 있음)
        data: Any = None
        try:
            # openai-python v1 Responses 객체는 structured JSON 접근 도우미 제공
            # 만약 없다면 아래처럼 텍스트를 파싱하거나 resp.output[0].content 를 확인.
            if hasattr(resp, "output") and resp.output:
                # output -> list of items (text/json). structured outputs일 땐 json 이 포함
                for item in resp.output:
                    if getattr(item, "type", "") == "output_text":
                        # 혹시 모델이 텍스트로 JSON을 준다면 fallback 파싱
                        data = _safe_json_parse(getattr(item, "text", ""))
                    elif getattr(item, "type", "") == "parsed_json":
                        data = getattr(item, "parsed", None)
                        break
            # 일부 SDK 버전/모델에서 바로 json이 제공될 수 있음
            if data is None and hasattr(resp, "output_parsed"):
                data = resp.output_parsed
        except Exception:
            pass

        if not data:
            # 최후: 전체 응답을 문자열로 만들고 JSON 추정 파싱 시도
            data = _safe_json_parse(str(resp))

        try:
            obj = SubjectiveScore.model_validate(data)
            return float(obj.score)
        except ValidationError:
            # 구조화 출력이 깨졌다면 텍스트 기반 파싱으로 폴백
            return _parse_score_from_text(str(data))


# =========================
# 6) 헬퍼 함수(파싱)
# =========================

def _safe_json_parse(s: str) -> Optional[dict]:
    try:
        return json.loads(s)
    except Exception:
        return None

def _parse_score_from_text(s: str) -> float:
    """
    최후의 안전장치: 텍스트에서 숫자만 뽑아 0~100으로 클램프.
    구조화 출력이 정상 동작하면 이 경로는 거의 타지 않음.
    """
    import re
    m = re.search(r"(\d+(?:\.\d+)?)", s or "")
    if not m:
        return 0.0
    v = float(m.group(1))
    return max(0.0, min(100.0, v))
