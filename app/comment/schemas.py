from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Union
from enum import Enum
from typing import List, Union

class CommentCreateRequest(BaseModel):
    user_id: str
    problem_id: int | None = None
    solve_id: int | None = None
    comment: str
    is_problem_message: bool = False

class CommentCreateResponse(BaseModel):
    comment_id: int
    user_id: str
    problem_id: int | None = None
    solve_id: int | None = None
    comment: str
    is_problem_message: bool
    created_at: datetime
    
    
#__________________________________________
# 코멘토 조회 problem_id 스키마

class _CommentBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # ORM ↔ 모델 변환 시 안전
    comment_id: int
    user_id: str
    comment: str
    is_problem_message: bool
    timestamp: datetime

class CommentGetProblemResponse(_CommentBase):
    problem_id: int
    # 🔧 문제 코멘트에서는 solve_id가 None일 수 있다
    solve_id: Optional[int] = Field(default=None)

class CommmentGetSolveResponse(_CommentBase):  # (클래스명이 Commment면 그대로 유지)
    solve_id: int
    # 🔧 제출 코멘트에서는 problem_id가 None일 수 있다
    problem_id: Optional[int] = Field(default=None)
    
#__________________________________________
class ConditionStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class OverallStatus(str, Enum):
    SUCCESS = "success"
    FAIL = "fail"


class ConditionResult(BaseModel):
    condition_id: int
    condition: str
    status: ConditionStatus
    description: str
    feedback: str
    score: float


class AIFeedbackResponse(BaseModel):
    solve_id: int
    ai_feedback: str
    total_score: float
    points: float
    condition_results: List[ConditionResult]
    all_status: OverallStatus
    
