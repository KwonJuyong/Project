from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict
from datetime import datetime
from sqlalchemy.ext.asyncio import create_async_engine

class WorkbookCreateRequest(BaseModel):
    workbook_name: str
    group_id: int
    description: str
    is_test_mode: bool
    test_start_time: Optional[datetime] = None
    test_end_time: Optional[datetime] = None
    
    publication_start_time: Optional[datetime] = None
    publication_end_time: Optional[datetime] = None

class WorkbookCreateResponse(BaseModel):
    msg: str
    workbook_id: int

# @router.get("/{workbook_id}" 에 해당되는 부분 
class WorkbookGetResponse(BaseModel):
    workbook_id: int
    group_id: int
    workbook_name: str
    problem_cnt:int
    creation_date: datetime
    description: str
    
    is_test_mode: bool
    test_start_time: Optional[datetime] = None
    test_end_time: Optional[datetime] = None
    publication_start_time: Optional[datetime] = None
    publication_end_time: Optional[datetime] = None
    workbook_total_points: float




class WorkbookUpdateRequest (BaseModel):
    workbook_name: str
    description: str
    test_start_time: Optional[datetime] = None
    test_end_time: Optional[datetime] = None
    publication_start_time: Optional[datetime] = None
    publication_end_time: Optional[datetime] = None

