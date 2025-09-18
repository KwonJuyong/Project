from pydantic import BaseModel

class RegisterCheckRequest(BaseModel):
    user_id: str
    email: str

class RegisterCheckResponse(BaseModel):
    is_user_exist: bool
    is_email_exist: bool
