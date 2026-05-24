from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    owner_id: str
    username: str
    expires_at: datetime


class RefreshResponse(BaseModel):
    expires_at: datetime
