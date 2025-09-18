from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict
from datetime import datetime
from enum import Enum
from sqlalchemy.ext.asyncio import create_async_engine
from app.problem.models.problem import ProblemTypeEnum

class ProblemReferenceCreate(BaseModel):
    group_id: int
    workbook_id: int
    problem_id: list[int]
    points: int


class ProblemReferenceGetRequest(BaseModel):
    group_id: int
    workbook_id: int


class ProblemShowResponse(BaseModel):
    problem_id: int
    title: str
    problem_type : ProblemTypeEnum
    description: str
    attempt_count: int
    pass_count: int
    points : int

    
class ProblemPointsUpdateRequest(BaseModel):
    points: float
    
class ProblemPointsUpdateResponse(BaseModel):
    message: str
    problem_id: int
    updated_points: float