import re
from enum import Enum

class RatingMode(str, Enum):
    HARD = "hard"
    SPACE = "space"
    REGEX = "regex"
    NONE = "none"

class problem_Normalization:
    @staticmethod
    def normalize_space(text: str) -> str:
        text = (text or "")
        # 개행을 공백으로 (선택사항: \s+로도 커버됨)
        text = text.replace('\n', ' ')
        # 연속 공백 1칸으로
        text = re.sub(r'\s+', ' ', text)
        # 괄호/대괄호/중괄호 주변 공백 제거 (안전하게 이스케이프)
        text = re.sub(r'\s*([\[\]\(\)\{\}])\s*', r'\1', text)
        # 쉼표 뒤 불필요 공백 제거
        text = re.sub(r',\s*', ',', text)
        return text.strip()

    @staticmethod
    def compare_hard(output: str, expected: str) -> bool:
        return (output or "").strip() == (expected or "").strip()

    @staticmethod
    def compare_space(output: str, expected: str) -> bool:
        normalized_output = problem_Normalization.normalize_space(output)
        normalized_expected = problem_Normalization.normalize_space(expected)
        return normalized_output == normalized_expected

    @staticmethod
    def compare_regex(output: str, expected: str) -> bool:
        try:
            pattern = re.compile((expected or "").strip(), flags=re.DOTALL | re.MULTILINE)
            return bool(pattern.fullmatch((output or "").strip()))
        except re.error:
            return False

    @classmethod
    def compare(cls, output: str, expected: str, rating_mode: RatingMode) -> bool:
        if rating_mode == RatingMode.HARD:
            return cls.compare_hard(output, expected)
        elif rating_mode == RatingMode.SPACE:
            return cls.compare_space(output, expected)
        elif rating_mode == RatingMode.REGEX:
            return cls.compare_regex(output, expected)
        elif rating_mode == RatingMode.NONE:
            # 비교 생략 정책
            return True
        return False
