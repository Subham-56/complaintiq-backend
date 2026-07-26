from pydantic import BaseModel, EmailStr
from typing import Literal

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    username: str
    admin_code: str | None = None

class LoginRequest(BaseModel):
    email: str
    password: str

class StatusUpdateRequest(BaseModel):
    status: Literal["Pending", "Under Review", "In Progress", "Resolved", "Rejected"]