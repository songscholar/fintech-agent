import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.dev.utils.db_utils import get_sys_db
from src.dev.utils.auth import get_current_user
from src.dev.database.models import User, Conversation, Message
from src.dev.api.dto import ConversationCreate, ConversationDTO, MessageDTO

router = APIRouter(prefix="/api/v1/chat", tags=["Chat Management"])


@router.post("/conversations", response_model=ConversationDTO)
def create_conversation(
        conv_in: ConversationCreate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_sys_db)
):
    """创建新会话"""
    session_id = str(uuid.uuid4())
    new_conv = Conversation(
        id=session_id,
        user_id=current_user.id,
        title=conv_in.title
    )
    db.add(new_conv)
    db.commit()
    db.refresh(new_conv)
    return new_conv


@router.get("/conversations", response_model=List[ConversationDTO])
def get_conversations(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_sys_db)
):
    """获取当前用户的所有会话列表"""
    return db.query(Conversation).filter(
        Conversation.user_id == current_user.id
    ).order_by(Conversation.updated_at.desc()).all()


@router.get("/conversations/{session_id}/messages", response_model=List[MessageDTO])
def get_history(
        session_id: str,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_sys_db)
):
    """获取指定会话的历史消息"""
    conv = db.query(Conversation).filter(
        Conversation.id == session_id,
        Conversation.user_id == current_user.id
    ).first()

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return db.query(Message).filter(
        Message.conversation_id == session_id
    ).order_by(Message.created_at.asc()).all()