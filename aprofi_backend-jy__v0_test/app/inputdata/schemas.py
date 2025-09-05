# app/inputdata/schemas.py
from typing import List, Optional, Union, Literal
from pydantic import BaseModel
from enum import Enum

# --------- Enums ---------
class ProblemTypeEnum(str, Enum):
    coding = "코딩"
    multiple_choice = "객관식"
    short_answer = "단답형"
    subjective = "주관식"
    debugging = "디버깅"

class CodingRatingModeEnum(str, Enum):
    space = "space"
    regex = "regex"
    hard = "hard"
    none = "none"

class ShortAnswerRatingModeEnum(str, Enum):
    exact = "exact"
    partial = "partial"
    soft = "soft"
    none = "none"

class SubjectiveRatingModeEnum(str, Enum):
    active = "active"
    deactive = "deactive"

# --------- 공통 모델 ---------
class ReferenceCode(BaseModel):
    language: str
    code: str
    is_main: bool

class TestCase(BaseModel):
    input: str
    expected_output: str

class BaseCode(BaseModel):
    language: str
    code: str

# --------- Base Problem ---------
class ProblemBaseRequest(BaseModel):
    title: str
    description: Optional[str] = None
    difficulty: Optional[str] = "easy"
    tags: List[str] = []
    prev_problem_id: Optional[int] = None

# --------- Problem Types ---------
class CodingProblemRequest(ProblemBaseRequest):
    problemType: Literal["코딩", "디버깅"]
    rating_mode: CodingRatingModeEnum
    reference_codes: List[ReferenceCode]
    problem_condition: List[str] = []
    test_cases: List[TestCase]
    base_code: List[BaseCode]

class MultipleChoiceRequest(ProblemBaseRequest):
    problemType: Literal["객관식"]
    options: List[str]
    correct_answers: List[int]
    rating_mode: Optional[str] = None

class ShortAnswerProblemRequest(ProblemBaseRequest):
    problemType: Literal["단답형"]
    rating_mode: ShortAnswerRatingModeEnum
    answer_text: List[str]
    grading_criteria: List[str]

class SubjectiveProblemRequest(ProblemBaseRequest):
    problemType: Literal["주관식"]
    rating_mode: SubjectiveRatingModeEnum
    answer_text: str
    grading_criteria: Optional[List[str]] = None

# --------- Input Data Request ---------
class InputDataRequest(BaseModel):
    problems: List[Union[CodingProblemRequest, MultipleChoiceRequest, ShortAnswerProblemRequest, SubjectiveProblemRequest]]

    class Config:
        min_anystr_length = 1
        anystr_strip_whitespace = True
