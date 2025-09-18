from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Annotated, Union
from datetime import datetime
from enum import Enum


class ProblemTypeEnum(str, Enum):
    coding = "코딩"
    multiple_choice = "객관식"
    short_answer = "단답형"
    subjective = "주관식"
    debugging = "디버깅"

# --------- Enums ---------
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

# --------- Request Schemas ---------

class baseCode(BaseModel):
    language: str
    code : str

class CodingProblemRequest(BaseModel):
    problemType: Literal["코딩","디버깅"]
    title: str
    description: str
    difficulty: str
    rating_mode: CodingRatingModeEnum
    tags: List[str] = []
    problem_condition: List[str] = []
    reference_codes: List[ReferenceCode] = []
    test_cases: List[TestCase] = []
    base_code: List[baseCode] = []

class multipleChoiceRequest(BaseModel):
    problemType: Literal["객관식"]
    title: str
    description: str
    difficulty: str
    tags: List[str] = []
    options: List[str]
    correct_answers: List[int]
    rating_mode: Optional[str] = None

class ShortAnswerProblemRequest(BaseModel):
    problemType: Literal["단답형"]
    title: str
    description: str
    difficulty: str
    rating_mode: ShortAnswerRatingModeEnum
    tags: List[str] = []
    answer_text: List[str]
    grading_criteria: List[str]

class SubjectiveProblemRequest(BaseModel):
    problemType: Literal["주관식"]
    title: str
    description: str
    difficulty: str
    rating_mode: SubjectiveRatingModeEnum
    answer_text: str
    tags: List[str] = []
    grading_criteria: Optional[List[str]] = None

# --------- Response Schemas ---------

class CodingProblemResponse(BaseModel):
    problem_id: int
    maker_id: str
    title: str
    description: str
    difficulty: str
    tags: List[str]
    problem_condition: List[str]
    created_at: datetime
    problemType: str
    rating_mode: str
    reference_codes: List[ReferenceCode]
    test_cases: List[TestCase]
    base_code: List[baseCode] = []

class MultipleChoiceResponse(BaseModel):
    problem_id: int
    maker_id: str
    title: str
    description: str
    difficulty: str
    tags: List[str]
    created_at: datetime
    problemType: str
    options: List[str]
    rating_mode: Optional[str] = None
    correct_answers: List[int]

class ShortAnswerProblemResponse(BaseModel):
    problem_id: int
    maker_id: str
    title: str
    description: str
    difficulty: str
    tags: List[str]
    created_at: datetime
    problemType: str
    rating_mode: ShortAnswerRatingModeEnum
    answer_text: List[str]
    grading_criteria: Optional[List[str]]

class SubjectiveProblemResponse(BaseModel):
    problem_id: int
    maker_id: str
    title: str
    description: str
    difficulty: str
    answer_text: str
    tags: List[str]
    created_at: datetime
    problemType: str
    rating_mode: str
    grading_criteria: Optional[List[str]]

# --------- Get Response Schemas ---------

class CodingProblemResponseGet(CodingProblemResponse):
    pass

class MultipleChoiceProblemResponseGet(MultipleChoiceResponse):
    rating_mode: str

class ShortAnswerProblemResponseGet(ShortAnswerProblemResponse):
    pass

class SubjectiveProblemResponseGet(SubjectiveProblemResponse):
    pass

# --------- Update Schemas ---------

class UpdateCodingProblemRequest(BaseModel):
    problemType: Literal["코딩", "디버깅"]
    title: str
    description: str
    difficulty: str
    rating_mode: CodingRatingModeEnum
    tags: List[str]
    problem_condition: List[str]
    reference_codes: List[ReferenceCode]
    test_cases: List[TestCase]
    base_code: Optional[str]

class UpdateMultipleChoiceProblemRequest(BaseModel):
    problemType: Literal["객관식"]
    title: str
    description: str
    difficulty: str
    tags: List[str]
    options: List[str]
    correct_answers: List[int]

class UpdateShortAnswerProblemRequest(BaseModel):
    problemType: Literal["단답형"]
    title: str
    description: str
    difficulty: str
    rating_mode: ShortAnswerRatingModeEnum
    tags: List[str]
    answer_texts: List[str]
    grading_criteria: List[str]

class UpdateSubjectiveProblemRequest(BaseModel):
    problemType: Literal["주관식"]
    title: str
    description: str
    difficulty: str
    rating_mode: SubjectiveRatingModeEnum
    tags: List[str]
    grading_criteria: List[str]
