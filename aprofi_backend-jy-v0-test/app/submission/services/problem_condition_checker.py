import re
from typing import List, Dict, Any, Optional, Sequence
from ..schemas import ProblemConditionCheck, ConditionCheckResult

class ConditionChecker:
    """문제 조건 충족 여부를 체크하는 서비스"""
    
    @staticmethod
    def check_code_analysis_condition(condition: ProblemConditionCheck, code: str) -> ConditionCheckResult:
        """코드 분석 기반 조건 체크"""
        condition_text = condition.condition.lower()
        code_lower = code.lower()
        
        if "for loop" in condition_text:
            passed = "for " in code_lower
            feedback = "코드에 for 루프가 포함되어 있습니다." if passed else "코드에 for 루프가 필요합니다."
        elif "while loop" in condition_text:
            passed = "while " in code_lower
            feedback = "코드에 while 루프가 포함되어 있습니다." if passed else "코드에 while 루프가 필요합니다."
        elif "function" in condition_text:
            passed = "def " in code_lower or "function" in code_lower
            feedback = "코드에 함수가 정의되어 있습니다." if passed else "코드에 함수 정의가 필요합니다."
        elif "recursion" in condition_text:
            # 재귀 함수 체크 (간단한 패턴 매칭)
            passed = re.search(r'def\s+\w+\s*\([^)]*\)\s*:.*\1\s*\(', code, re.DOTALL) is not None
            feedback = "코드에 재귀 함수가 포함되어 있습니다." if passed else "코드에 재귀 함수가 필요합니다."
        elif "time complexity" in condition_text:
            # 시간 복잡도 체크 (간단한 패턴)
            if "o(n)" in condition_text:
                passed = "for " in code_lower and "in " in code_lower
                feedback = "O(n) 시간 복잡도를 만족합니다." if passed else "O(n) 시간 복잡도가 필요합니다."
            elif "o(1)" in condition_text:
                passed = "for " not in code_lower and "while " not in code_lower
                feedback = "O(1) 시간 복잡도를 만족합니다." if passed else "O(1) 시간 복잡도가 필요합니다."
            else:
                passed = True
                feedback = "시간 복잡도 조건을 확인할 수 없습니다."
        else:
            # 일반적인 키워드 체크
            keywords = condition_text.split()
            passed = all(keyword in code_lower for keyword in keywords)
            feedback = f"조건 '{condition.condition}'을 만족합니다." if passed else f"조건 '{condition.condition}'이 필요합니다."
        
        return ConditionCheckResult(
            condition=condition.condition,
            is_required=condition.is_required,
            check_type=condition.check_type,
            description=condition.description,
            passed=passed,
            feedback=feedback
        )
    
    @staticmethod
    def check_output_validation_condition(condition: ProblemConditionCheck, output: str, expected: str) -> ConditionCheckResult:
        """출력 검증 기반 조건 체크"""
        condition_text = condition.condition.lower()
        
        if "exact match" in condition_text:
            passed = output.strip() == expected.strip()
            feedback = "출력이 정확히 일치합니다." if passed else "출력이 정확히 일치하지 않습니다."
        elif "contains" in condition_text:
            # 특정 문자열 포함 여부 체크
            target = condition_text.split("contains")[-1].strip()
            passed = target in output
            feedback = f"출력에 '{target}'이 포함되어 있습니다." if passed else f"출력에 '{target}'이 포함되어야 합니다."
        elif "format" in condition_text:
            # 특정 형식 체크
            if "array" in condition_text:
                passed = re.match(r'^\[.*\]$', output.strip()) is not None
                feedback = "출력이 배열 형식입니다." if passed else "출력이 배열 형식이어야 합니다."
            elif "number" in condition_text:
                passed = output.strip().isdigit()
                feedback = "출력이 숫자 형식입니다." if passed else "출력이 숫자 형식이어야 합니다."
            else:
                passed = True
                feedback = "형식 조건을 확인할 수 없습니다."
        else:
            passed = True
            feedback = "출력 검증 조건을 확인할 수 없습니다."
        
        return ConditionCheckResult(
            condition=condition.condition,
            is_required=condition.is_required,
            check_type=condition.check_type,
            description=condition.description,
            passed=passed,
            feedback=feedback
        )
    
    @staticmethod
    def check_performance_condition(condition: ProblemConditionCheck, execution_time: float) -> ConditionCheckResult:
        """성능 기반 조건 체크"""
        condition_text = condition.condition.lower()
        
        if "time limit" in condition_text:
            # 시간 제한 체크
            time_limit = float(re.search(r'(\d+(?:\.\d+)?)', condition_text).group(1))
            passed = execution_time <= time_limit
            feedback = f"실행 시간({execution_time}ms)이 제한({time_limit}ms) 내에 있습니다." if passed else f"실행 시간({execution_time}ms)이 제한({time_limit}ms)을 초과했습니다."
        else:
            passed = True
            feedback = "성능 조건을 확인할 수 없습니다."
        
        return ConditionCheckResult(
            condition=condition.condition,
            is_required=condition.is_required,
            check_type=condition.check_type,
            description=condition.description,
            passed=passed,
            feedback=feedback
        )
    
    @classmethod
    def check_all_conditions(
        cls,
        conditions: Sequence[ProblemConditionCheck],  # List -> Sequence (공변성 + 읽기 전용 의도)
        code: str,
        output: Optional[str] = None,                # Optional 허용
        expected_output: Optional[str] = None,       # Optional 허용
        execution_time: float = 0.0
    ) -> List[ConditionCheckResult]:
        """모든 조건을 체크"""

        # --- 안전 정규화 (None -> "") ---
        out_str = output or ""
        exp_str = expected_output or ""

        results: List[ConditionCheckResult] = []

        for condition in conditions:
            if condition.check_type == "code_analysis":
                result = cls.check_code_analysis_condition(condition, code)
            elif condition.check_type == "output_validation":
                result = cls.check_output_validation_condition(condition, out_str, exp_str)
            elif condition.check_type == "performance":
                result = cls.check_performance_condition(condition, execution_time)
            else:
                # 기본적으로 통과로 처리
                result = ConditionCheckResult(
                    condition=condition.condition,
                    is_required=condition.is_required,
                    check_type=condition.check_type,
                    description=condition.description,
                    passed=True,
                    feedback="조건을 확인할 수 없습니다."
                )

            results.append(result)

        return results