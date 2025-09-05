from pydantic import BaseModel, Field
from typing import Union, List, Optional
from typing_extensions import Annotated
from enum import Enum
from typing import Literal
from datetime import datetime
from app.problem.schemas import CodingRatingModeEnum, TestCase

#ai_________________________________________________________________________________
class ConditionCheckResult(BaseModel):
    condition: str                      # 조건 문자열
    is_required: bool = True            # 필수 여부
    check_type: str = "gpt_check"       # 체크 타입 (예: gpt_check, code_analysis 등)
    description: Optional[str] = None   # 조건 설명
    passed: bool                        # 충족 여부
    feedback: Optional[str] = None      # 피드백 메시지
    

class ProblemConditionCheck(BaseModel):
    """
    문제에 설정된 '조건' 1개
    - check_type: code_analysis | output_validation | performance | gpt_check
    - 예) condition="for loop", "time limit 200", "exact match", ...
    """
    condition: str
    is_required: bool = True
    check_type: Literal["code_analysis", "output_validation", "performance", "gpt_check"] = "code_analysis"
    description: Optional[str] = None

    model_config = {"extra": "forbid"}
#_________________________________________________________________

class ProblemTypeKOR(str, Enum):
    coding = "코딩"
    debugging = "디버깅"
    multiple_choice = "객관식"
    short_answer = "단답형"
    subjective = "주관식"

# Pydantic v2: 공통 설정(불필요 키 거부)
class _ReqBase(BaseModel):
    model_config = {"extra": "forbid"}

# 베이스 클래스 없음! 각 모델 독립 정의 + Literal 고정
class CodingSolveRequest(_ReqBase):
    user_id: Optional[str] = None  # 서버에서 덮어씌움
    problemType: Literal[ProblemTypeKOR.coding]
    codes: str
    code_language: str

class DebuggingSolveRequest(_ReqBase):
    user_id: Optional[str] = None
    problemType: Literal[ProblemTypeKOR.debugging]
    codes: str
    code_language: str

class MultipleChoiceSolveRequest(_ReqBase):
    user_id: Optional[str] = None
    problemType: Literal[ProblemTypeKOR.multiple_choice]
    selected_options: List[int]

class ShortAnswerSolveRequest(_ReqBase):
    user_id: Optional[str] = None
    problemType: Literal[ProblemTypeKOR.short_answer]
    answer_text: str

class SubjectiveSolveRequest(_ReqBase):
    user_id: Optional[str] = None
    problemType: Literal[ProblemTypeKOR.subjective]
    written_text: str

SolveRequestUnion = Annotated[
    Union[
        CodingSolveRequest,
        DebuggingSolveRequest,
        MultipleChoiceSolveRequest,
        ShortAnswerSolveRequest,
        SubjectiveSolveRequest,
    ],
    Field(discriminator="problemType"),
]

class SolveResponse(BaseModel):
    solve_id: int
    problem_id: int
    user_id: str
    submitted_at: datetime  # ← FastAPI가 ISO로 직렬화
    result: Literal["correct", "wrong"]


#______________________________________________________________________

class SolveBaseResponseMe(BaseModel):
    solve_id: int
    problem_id: int
    problem_name: str
    group_id: int
    group_name: str
    workbook_id: int
    workbook_name: str
    user_id: str
    timestamp: datetime
    passed: bool


# ---------- 코딩 / 디버깅 ----------
class CodingSolveResponseMe(SolveBaseResponseMe):
    problemType: Literal["코딩"]
    code_language: str
    code_len: int


class DebuggingSolveResponseMe(SolveBaseResponseMe):
    problemType: Literal["디버깅"]
    code_language: str
    code_len: int


# ---------- 객관식 / 단답형 / 주관식 ----------
class MultipleChoiceSolveResponseMe(SolveBaseResponseMe):
    problemType: Literal["객관식"]


class ShortAnswerSolveResponseMe(SolveBaseResponseMe):
    problemType: Literal["단답형"]


class SubjectiveSolveResponseMe(SolveBaseResponseMe):
    problemType: Literal["주관식"]


# ---------- 최종 Union ----------
SolveResponseUnionMe = Union[
    CodingSolveResponseMe,
    DebuggingSolveResponseMe,
    MultipleChoiceSolveResponseMe,
    ShortAnswerSolveResponseMe,
    SubjectiveSolveResponseMe,
]

#______________________________________________________________-

class TestCaseResult(BaseModel):
    output: str
    passed : bool

#run code API용 스키마
class RunCodeRequest(BaseModel):
    language: str
    code: str
    rating_mode: CodingRatingModeEnum
    testcases: List[TestCase] = []
    
class RunCodeResponse(BaseModel):
    results: List[TestCaseResult] = []
    
#________________________________________________________________________
class getAllSubmissionsResponse(BaseModel):
    submission_id: int
    user_id: str
    problem_id: int
    score: float
    reviewed: bool
    created_at: datetime
    updated_at: datetime
    
    
#________________________________________________________________________
# submisson score 관련 스키마
class SubmissionScoreCreateRequest(BaseModel):
    score: float
    prof_feedback: str
    
class SubmissionScoreResponse(BaseModel):
    submission_score_id: int
    submission_id: int
    score: float
    prof_feedback: str
    graded_by: str
    created_at: datetime
    
#________________________________________________________
class SubmissionGetScoreResponse(BaseModel):
    submission_score_id: int
    submission_id: int
    score: float
    prof_feedback: str
    graded_by: str
    created_at: datetime