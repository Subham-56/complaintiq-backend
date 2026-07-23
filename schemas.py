from typing import Literal
from pydantic import BaseModel, EmailStr

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

class ComplaintResponse(BaseModel):
    id: int
    description: str
    latitude: float
    longitude: float
    issue_type: str
    ai_category: str | None
    ai_urgency: str | None
    ai_department: str | None
    status: str
    image_url: str | None
    upvote_count: int
    user_has_upvoted: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True

class AdminComplaintResponse(ComplaintResponse):
    user_id: int
    username: str
    email: str