from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class User(Base):
    """用户表"""
    __tablename__ = "sys_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    email = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

    # 关联会话
    conversations = relationship("Conversation", back_populates="user")

class Conversation(Base):
    """会话表 (代表一个聊天窗口)"""
    __tablename__ = "sys_conversations"

    id = Column(String(50), primary_key=True, index=True)  # 使用 UUID 或生成的 session_id
    user_id = Column(Integer, ForeignKey("sys_users.id"))
    title = Column(String(100), nullable=True) # 会话标题 (如: "关于ETF的查询")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

class Message(Base):
    """消息表 (存储具体的问答历史)"""
    __tablename__ = "sys_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(String(50), ForeignKey("sys_conversations.id"))
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)     # 消息内容
    msg_type = Column(String(20), default="text") # text, log_analysis, sql_result
    created_at = Column(DateTime, default=datetime.now)

    conversation = relationship("Conversation", back_populates="messages")