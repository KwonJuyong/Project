from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field
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

class CommentGetProblemResponse(BaseModel):
    comment_id: int
    user_id: str
    problem_id: int
    solve_id: int 
    comment: str
    is_problem_message: bool
    timestamp: datetime
    
class CommmentGetSolveResponse(BaseModel):
    comment_id: int
    user_id: str
    problem_id: int 
    solve_id: int 
    comment: str
    is_problem_message: bool
    timestamp: datetime
    
    
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