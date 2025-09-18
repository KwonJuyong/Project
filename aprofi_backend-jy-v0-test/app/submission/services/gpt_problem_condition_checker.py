import openai
import json
import os
from typing import List, Dict, Any
from ..schemas import ConditionCheckResult
from openai import AsyncOpenAI

class GPTConditionChecker:
    """GPT API를 활용한 코드 조건 체크 서비스"""
    
    def __init__(self):
        # settings 객체 대신 환경변수 직접 사용
        OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
        if not OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        self.client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    
    async def check_conditions_with_gpt(
        self,
        conditions: List[str],
        code: str,
        language: str,
        problem_description: str = ""
    ) -> List[ConditionCheckResult]:
        """GPT를 사용하여 코드 조건 체크"""
        
        results = []
        
        for condition in conditions:
            try:
                result = await self._check_single_condition(
                    condition=condition,
                    code=code,
                    language=language,
                    problem_description=problem_description
                )
                results.append(result)
            except Exception as e:
                print(f"Failed to check condition '{condition}': {e}")
                # 실패 시 기본 결과 생성
                results.append(ConditionCheckResult(
                    condition=condition,
                    is_required=True,
                    check_type="gpt_check",
                    description=condition,
                    passed=False,
                    feedback=f"조건 체크 중 오류 발생: {str(e)}"
                ))
        
        return results
    
    async def _check_single_condition(
        self,
        condition: str,
        code: str,
        language: str,
        problem_description: str
    ) -> ConditionCheckResult:
        """단일 조건을 GPT로 체크"""
        
        prompt = f"""
당신은 프로그래밍 코드 분석 전문가입니다. 주어진 코드가 특정 조건을 만족하는지 분석해주세요.

## 문제 설명
{problem_description}

## 프로그래밍 언어
{language}

## 체크할 조건
{condition}

## 분석할 코드
```{language}
{code}
```

## 분석 요청사항
1. 위 코드가 "{condition}" 조건을 만족하는지 판단하세요
2. 만족한다면 passed: true, confidence: 0.8-1.0 사이 값
3. 부분적으로 만족한다면 passed: false, confidence: 0.3-0.7 사이 값  
4. 전혀 만족하지 않는다면 passed: false, confidence: 0.0-0.2 사이 값
5. 구체적인 피드백을 제공하세요

## 응답 형식 (JSON)
{{
    "passed": boolean,
    "confidence": float (0.0-1.0),
    "feedback": "구체적인 분석 결과와 피드백",
    "analysis": "코드 분석 내용"
}}

JSON 형식으로만 응답해주세요.
"""
        
        try:
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "당신은 프로그래밍 코드 분석 전문가입니다. JSON 형식으로만 응답하세요."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=500
            )
            
            # JSON 파싱
            content = response.choices[0].message.content.strip()
            result_data = json.loads(content)
            
            return ConditionCheckResult(
                condition=condition,
                is_required=True,
                check_type="gpt_check",
                description=condition,
                passed=result_data.get("passed", False),
                feedback=result_data.get("feedback", "분석 결과 없음")
            )
            
        except json.JSONDecodeError as e:
            # JSON 파싱 실패 시 기본 결과
            return ConditionCheckResult(
                condition=condition,
                is_required=True,
                check_type="gpt_check",
                description=condition,
                passed=False,
                feedback=f"GPT 응답 파싱 실패: {str(e)}"
            )
        except Exception as e:
            # 기타 오류
            return ConditionCheckResult(
                condition=condition,
                is_required=True,
                check_type="gpt_check",
                description=condition,
                passed=False,
                feedback=f"GPT 분석 중 오류: {str(e)}"
            )
    
    async def check_all_conditions_batch(
        self,
        conditions: List[str],
        code: str,
        language: str,
        problem_description: str = "",
        problem_conditions_check: List = None
    ) -> List[ConditionCheckResult]:
        """모든 조건을 한 번에 GPT로 체크 (배치 처리)"""
        
        prompt = f"""
당신은 프로그래밍 코드 분석 전문가입니다. 주어진 코드가 여러 조건을 만족하는지 분석해주세요.

## 문제 설명
{problem_description}

## 프로그래밍 언어
{language}

## 체크할 조건들
{chr(10).join([f"{i+1}. {condition}" for i, condition in enumerate(conditions)])}

## 분석할 코드
```{language}
{code}
```

## 분석 요청사항
각 조건에 대해 다음을 분석하세요:
1. 조건 만족 여부 (passed: true/false)
2. 신뢰도 (confidence: 0.0-1.0)
3. 구체적인 피드백

## 응답 형식 (JSON)
{{
    "results": [
        {{
            "condition": "조건 내용",
            "passed": boolean,
            "confidence": float,
            "feedback": "구체적인 분석 결과와 피드백"
        }}
    ]
}}

JSON 형식으로만 응답해주세요.
"""
        
        try:
            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "당신은 프로그래밍 코드 분석 전문가입니다. JSON 형식으로만 응답하세요."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content.strip()
            result_data = json.loads(content)
            
            results = []
            for i, result in enumerate(result_data.get("results", [])):
                # problem_conditions_check에서 해당 조건의 정보 가져오기 (있는 경우)
                condition_info = None
                if problem_conditions_check and i < len(problem_conditions_check):
                    condition_info = problem_conditions_check[i]
                
                # problem_condition의 문자열 조건 처리
                condition_text = conditions[i] if i < len(conditions) else result.get("condition", "")
                
                results.append(ConditionCheckResult(
                    condition=condition_text,
                    is_required=condition_info.is_required if condition_info else True,
                    check_type=condition_info.check_type if condition_info else "code_analysis",
                    description=condition_info.description if condition_info else condition_text,
                    passed=result.get("passed", False),
                    feedback=result.get("feedback", "분석 결과 없음")
                ))
            
            return results
            
        except Exception as e:
            print(f"Batch condition check failed: {e}")
            # 실패 시 개별 체크로 폴백
            return await self.check_conditions_with_gpt(conditions, code, language, problem_description) 