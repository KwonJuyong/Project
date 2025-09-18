from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class PresenceUserBase(BaseModel):
    userId: str
    nickname: Optional[str]
    userAgent: Optional[str]
    ipAddress: Optional[str]

class UserSessionBase(BaseModel):
    userId: str = Field(alias="user_id")
    page: Optional[str]
    duration: Optional[float]
    ipAddress: Optional[str] = Field(alias="ip_address")
    userAgent: Optional[str] = Field(alias="user_agent")
    createdAt: Optional[datetime] = Field(alias="created_at")
    status: Optional[str]
    
    model_config = {
        "from_attributes": True,
        "populate_by_name": True
    }
class UserSessionCreate(UserSessionBase):
    
    model_config = {
        "from_attributes": True,
        "populate_by_name": True
    }

