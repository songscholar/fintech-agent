from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class UserRegister(BaseModel):
    username: str
    password: str
    email: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    username: str


class ConversationCreate(BaseModel):
    title: Optional[str] = "新建对话"


class MessageDTO(BaseModel):
    role: str
    content: str
    msg_type: str
    created_at: datetime

    class Config:
        orm_mode = True


class ConversationDTO(BaseModel):
    id: str
    title: str
    created_at: datetime

    class Config:
        orm_mode = True