from datetime import datetime
from typing import List
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class CodeLogsRequest(BaseModel):
    solve_id: int
    user_id: str
    code_logs: list[str]
    timestamp: list[datetime]

class CodeLogsResponse(BaseModel):
    code: str
    timestamp: datetime