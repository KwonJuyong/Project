from pydantic import BaseModel, Field, ConfigDict
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
    multiple_choice = "객관식"
    short_answer = "단답형"
    subjective = "주관식"
    debugging = "디버깅"

# Pydantic v2: 공통 설정(불필요 키 거부)
class _ReqBase(BaseModel):
    model_config = {"extra": "forbid"}

# 베이스 클래스 없음! 각 모델 독립 정의 + Literal 고정
class CodingSolveRequest(_ReqBase):
    user_id: Optional[str] = None  # 서버에서 덮어씌움
    problemType: Literal["코딩", "coding"]
    codes: str
    code_language: str

class DebuggingSolveRequest(_ReqBase):
    user_id: Optional[str] = None
    problemType: Literal["디버깅","debugging"]
    codes: str
    code_language: str

class MultipleChoiceSolveRequest(_ReqBase):
    user_id: Optional[str] = None
    problemType: Literal["multiple_choice","객관식"]
    selected_options: List[int]

class ShortAnswerSolveRequest(_ReqBase):
    user_id: Optional[str] = None
    problemType: Literal["short_answer","단답형"]
    answer_text: List[str]

class SubjectiveSolveRequest(_ReqBase):
    user_id: Optional[str] = None
    problemType: Literal["subjective","주관식"]
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

class ExecutionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    TIMEOUT = "TIMEOUT"
    ERROR   = "ERROR"


class OverallStatus(str, Enum):
    success = "success"
    partial = "partial"
    failed  = "failed"


class RatingMode(str, Enum):
    HARD  = "hard"
    SPACE = "space"
    REGEX = "regex"
    NONE  = "none"


# 요청용
class TestCaseInput(BaseModel):
    input: str
    expected_output: str

class RunCodeRequest(BaseModel):
    group_id: int
    workbook_id: int
    problem_id: int
    language: str
    code: str
    rating_mode: str
    test_cases: List[TestCaseInput] = Field(default_factory=list, alias="test_cases")
    testcases:  List[TestCaseInput] = Field(default_factory=list)  # 구버전 호환
    model_config = ConfigDict(populate_by_name=True)

# 응답용(프론트가 쓰는 요약 결과)
class TestCaseResult(BaseModel):
    output: str
    passed: bool

class RunCodeResponse(BaseModel):
    results: List[TestCaseResult] = Field(default_factory=list)

# 러너 내부 리치 결과(로그/정규화용)
class RunnerTestResult(BaseModel):
    test_case_index: int
    status: Literal["SUCCESS", "TIMEOUT", "ERROR"]
    output: str
    error: Optional[str] = None
    execution_time: float  # ms
    memory_usage: int      # bytes
    passed: bool
    input: str = ""                # 로그 보강용
    expected_output: str = ""      # 로그 보강용

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
    
#________________________________________________________
#컴파일러
class TestCaseInput(BaseModel):
    input: str
    expected_output: str
    
class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    

class RatingMode(str, Enum):
    HARD = "Hard"
    SPACE = "Space"
    REGEX = "Regex"
    NONE = "None"
    
#________________________________________________________
# -----------------------------
# 공통 Enum/타입
# -----------------------------
class OverallStatus(str, Enum):
    success = "success"
    failed = "failed"
    partial = "partial"
    error = "error"


class ConditionCheckType(str, Enum):
    static = "static"
    rule = "rule"
    rubric = "rubric"
    runtime = "runtime"


class ConditionCheckResultRef(BaseModel):
    condition: str = Field(..., description="체크한 조건 이름")
    is_required: bool = Field(..., description="필수 조건 여부")
    check_type: ConditionCheckType = Field(..., description="체크 방식")
    description: str = Field("", description="조건 설명")
    passed: bool = Field(..., description="충족 여부")
    feedback: str = Field("", description="조건별 피드백(선택)")


# -----------------------------
# 코딩/디버깅 전용 타입
# -----------------------------
class CodingTestCase(BaseModel):
    input: str = Field("", description="표준 입력")
    expected_output: str = Field("", description="기대 출력(개행 정규화 전)")


class CodingTestResult(BaseModel):
    input: str = Field("", description="테스트 입력")
    actual_output: str = Field("", description="실제 프로그램 출력")
    passed: bool = Field(..., description="통과 여부")
    exec_time_ms: float = Field(0, description="실행 시간(ms)")
    # 필요 시 확장 가능: memory_usage, status, error 등

