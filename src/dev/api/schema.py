from typing import Optional, Dict, Any, List, Union
from pydantic import BaseModel, Field


# ==================== 通用响应 ====================
class StandardResponse(BaseModel):
    code: int = 200
    message: str = "success"
    data: Optional[Any] = None


# ==================== 1. 日志分析模块 ====================
class LogAnalysisRequest(BaseModel):
    log_content: str = Field(..., description="原始日志内容", min_length=10)
    session_id: Optional[str] = None


class LogAnalysisResult(BaseModel):
    summary: str
    error_code: str
    log_type: str
    report: str
    is_success: bool
    session_id: str
    evaluation_score: int


# ==================== 2. 智能问答模块 (QA) ====================
class QARequest(BaseModel):
    question: str = Field(..., description="用户的问题", min_length=1)
    session_id: Optional[str] = None


class QAResult(BaseModel):
    answer: str
    session_id: str
    question_type: str = Field(..., description="business(业务) 或 general(通用)")
    validated: bool = Field(..., description="答案是否通过校验")
    context_used: bool = Field(..., description="是否引用了知识库/联网信息")


# ==================== 3. 数据库操作模块 (SQL) ====================
class SQLRequest(BaseModel):
    question: str = Field(..., description="自然语言查询指令", min_length=1)
    session_id: Optional[str] = None
    # 可选：指定数据源，未来可支持多库切换
    # db_alias: str = "default"


class SQLResult(BaseModel):
    answer: str
    session_id: str
    sql_generated: Optional[str] = None
    sql_type: Optional[str] = None
    requires_human_approval: bool
    human_approved: bool
    execution_success: bool
    row_count: int
    error: Optional[str] = None

    # 如果需要审核，前端可以用这个字段判断是否弹出确认框
    approval_ticket_id: Optional[int] = None


# --- SQL 人工审核相关 ---
class SQLApprovalRequest(BaseModel):
    ticket_id: int = Field(..., description="审核单ID (对应 pending_approvals 的 index)")
    approve: bool = Field(True, description="是否批准执行")
    comments: Optional[str] = Field(None, description="审核意见")


class SQLPendingItem(BaseModel):
    index: int
    sql: str
    reason: str
    timestamp: str
    session_id: str