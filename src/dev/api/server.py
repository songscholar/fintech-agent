import os
from datetime import datetime

from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

from src.dev.api.routers import auth_router, chat_router
from src.dev.utils.db_utils import init_sys_db, get_sys_db
from src.dev.utils.auth import get_current_user
from src.dev.database.models import User, Message, Conversation
from dotenv import load_dotenv

# 导入 schema
from src.dev.api.schema import (
    StandardResponse,
    LogAnalysisRequest, LogAnalysisResult,
    QARequest, QAResult,
    SQLRequest, SQLResult, SQLApprovalRequest, SQLPendingItem
)

# 导入三个 Agent 类
from src.dev.agent.log_agent import LogAnalysisAgent
from src.dev.agent.qa_agent import FinancialQAAssistant
from src.dev.agent.sql_agent import DatabaseAgent

# 加载环境变量
load_dotenv()

app = FastAPI(
    title="Enterprise AI Agent Platform",
    description="集成了日志分析、智能问答与数据库操作的统一服务平台",
    version="3.0.0"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= 全局 Agent 实例 =================
agents = {
    "log": None,
    "qa": None,
    "sql": None
}


@app.on_event("startup")
async def startup_event():
    print("\n🚀 [系统启动] 正在初始化所有智能体...")

    # 1. 初始化日志智能体
    try:
        agents["log"] = LogAnalysisAgent()
        print("✅ 日志分析智能体 (LogAgent) 就绪")
    except Exception as e:
        print(f"❌ 日志智能体初始化失败: {e}")

    # 2. 初始化 QA 智能体
    try:
        agents["qa"] = FinancialQAAssistant()
        print("✅ 智能问答助手 (QAAgent) 就绪")
    except Exception as e:
        print(f"❌ QA智能体初始化失败: {e}")

    # 3. 初始化 SQL 智能体
    try:
        # 从环境变量获取数据库连接串，默认使用内存数据库用于演示
        db_conn = os.getenv("DB_CONNECTION_STRING", "sqlite:///:memory:")
        agents["sql"] = DatabaseAgent(db_connection_string=db_conn)
        print(f"✅ 数据库智能体 (SQLAgent) 就绪 (连接: {db_conn.split('@')[-1]})")
    except Exception as e:
        print(f"❌ SQL智能体初始化失败: {e}")

    print("✨ 所有服务加载完成!\n")


# ==================== 1. 日志分析接口 ====================
@app.post("/api/v1/log/analyze", response_model=StandardResponse)
async def analyze_log(request: LogAnalysisRequest):
    if not agents["log"]:
        raise HTTPException(503, "Log Agent not initialized")

    try:
        result = agents["log"].analyze(request.log_content, request.session_id)

        if not result["success"]:
            return StandardResponse(code=500, message=result.get("error", "Failed"))

        data = LogAnalysisResult(
            summary=result["parsed_data"].get("summary", ""),
            error_code=result["parsed_data"].get("error_code", ""),
            log_type=result.get("log_type", "UNKNOWN"),
            report=result.get("report", ""),
            is_success=True,
            session_id=result.get("session_id"),
            evaluation_score=result.get("eval_score", 0)
        )
        return StandardResponse(data=data)
    except Exception as e:
        return StandardResponse(code=500, message=str(e))


# ==================== 2. 智能问答接口 ====================
@app.post("/api/v1/qa/ask", response_model=StandardResponse)
async def ask_qa(request: QARequest):
    """
    业务/通用问答入口
    """
    if not agents["qa"]:
        raise HTTPException(503, "QA Agent not initialized")

    try:
        # 调用 QA Agent
        result = agents["qa"].ask(request.question, request.session_id)

        data = QAResult(
            answer=result["answer"],
            session_id=result["session_id"],
            question_type=result.get("question_type", "general"),
            validated=result.get("validated", False),
            context_used=result.get("context_used", False)
        )
        return StandardResponse(data=data)
    except Exception as e:
        return StandardResponse(code=500, message=str(e))


# ==================== 3. 数据库操作接口 ====================
@app.post("/api/v1/sql/ask", response_model=StandardResponse)
async def ask_sql(request: SQLRequest):
    """
    数据库自然语言查询
    """
    if not agents["sql"]:
        raise HTTPException(503, "SQL Agent not initialized")

    try:
        # 调用 SQL Agent
        result = agents["sql"].ask(request.question, request.session_id)

        # 构造返回结果
        data = SQLResult(
            answer=result["answer"],
            session_id=result["session_id"],
            sql_generated=result.get("sql_generated"),
            sql_type=result.get("sql_type"),
            requires_human_approval=result.get("requires_human_approval", False),
            human_approved=result.get("human_approved", False),
            execution_success=result.get("execution_success", False),
            row_count=result.get("row_count", 0),
            error=result.get("error")
        )

        # 如果进入了审核队列，尝试获取 Ticket ID (通常是 pending 列表的最后一个)
        # 实际生产中建议在 ask 返回结果中直接带上 ticket_id，这里做一个简单的推断
        if data.requires_human_approval and not data.human_approved:
            pending = agents["sql"].get_pending_approvals()
            if pending:
                # 假设当前请求对应最后一个待审核项
                data.approval_ticket_id = pending[-1]["index"]

        return StandardResponse(data=data)
    except Exception as e:
        return StandardResponse(code=500, message=str(e))


@app.get("/api/v1/sql/pending", response_model=StandardResponse)
async def get_pending_approvals():
    """获取待人工审核的 SQL 列表"""
    if not agents["sql"]:
        raise HTTPException(503, "SQL Agent not initialized")

    pending_list = agents["sql"].get_pending_approvals()
    # 转换模型
    data = [
        SQLPendingItem(
            index=item["index"],
            sql=item["sql"],
            reason=item["reason"],
            timestamp=item.get("timestamp", ""),
            session_id=item.get("session_id", "")
        ) for item in pending_list
    ]
    return StandardResponse(data=data)


@app.post("/api/v1/sql/approve", response_model=StandardResponse)
async def approve_sql(request: SQLApprovalRequest):
    """
    提交人工审核结果 (通过/拒绝)
    """
    if not agents["sql"]:
        raise HTTPException(503, "SQL Agent not initialized")

    result = agents["sql"].approve_sql(
        approval_index=request.ticket_id,
        approve=request.approve,
        comments=request.comments
    )

    if not result["success"]:
        return StandardResponse(code=400, message=result.get("error"))

    # 如果批准并通过，result 里会有执行结果
    return StandardResponse(data=result)


# ==================== 健康检查 ====================
@app.get("/health")
async def health_check():
    status = {
        "service": "running",
        "agents": {
            "log": agents["log"] is not None,
            "qa": agents["qa"] is not None,
            "sql": agents["sql"] is not None
        }
    }
    return status  # 初始化系统表


init_sys_db()

app = FastAPI(title="Enterprise AI Agent Platform", version="3.1.0")

# 注册路由
app.include_router(auth_router.router)
app.include_router(chat_router.router)


# ... (CORS 配置等保持不变)

# ==================== 辅助函数：保存聊天记录 ====================
def save_chat_history(db: Session, session_id: str, user_input: str, ai_output: str, user_id: int,
                      msg_type: str = "text"):
    """将对话持久化到数据库"""
    # 1. 检查会话是否存在，不存在则自动创建（兼容性逻辑）
    conv = db.query(Conversation).filter(Conversation.id == session_id).first()
    if not conv:
        conv = Conversation(id=session_id, user_id=user_id, title=user_input[:20])
        db.add(conv)
        db.commit()

    # 2. 保存用户消息
    user_msg = Message(conversation_id=session_id, role="user", content=user_input, msg_type="text")
    db.add(user_msg)

    # 3. 保存 AI 消息
    ai_msg = Message(conversation_id=session_id, role="assistant", content=ai_output, msg_type=msg_type)
    db.add(ai_msg)

    # 4. 更新会话时间
    conv.updated_at = datetime.now()
    db.commit()


# ==================== 修改原有接口：增加鉴权和保存 ====================

@app.post("/api/v1/qa/ask", response_model=StandardResponse)
async def ask_qa(
        request: QARequest,
        current_user: User = Depends(get_current_user),  # 🔒 强制鉴权
        db: Session = Depends(get_sys_db)
):
    # ... (初始化检查逻辑不变)

    # 调用 Agent
    # 💡 优化：这里可以从 db 查询历史消息，构建 chat_history 传给 Agent，
    # 但由于我们的 Agent 内部有 MemoryManager，暂时可以依赖 Agent 内部逻辑，
    # 也可以选择在这里将 SQL 里的历史注入给 Agent。
    result = agents["qa"].ask(request.question, request.session_id)

    # 💾 持久化保存
    save_chat_history(
        db,
        request.session_id,
        request.question,
        result["answer"],
        current_user.id,
        "qa"
    )

    # ... (返回逻辑不变)
    return StandardResponse(data=QAResult(**result))  # 适配一下字段


@app.post("/api/v1/sql/ask", response_model=StandardResponse)
async def ask_sql(
        request: SQLRequest,
        current_user: User = Depends(get_current_user),  # 🔒 强制鉴权
        db: Session = Depends(get_sys_db)
):
    # ... (Agent 调用逻辑)
    result = agents["sql"].ask(request.question, request.session_id)

    # 💾 持久化保存
    # 注意：如果需要审核，answer 可能是 "等待审核中..."
    save_chat_history(
        db,
        request.session_id,
        request.question,
        result["answer"],
        current_user.id,
        "sql"
    )

    # ... (返回逻辑)


@app.post("/api/v1/log/analyze", response_model=StandardResponse)
async def analyze_log(
        request: LogAnalysisRequest,
        current_user: User = Depends(get_current_user),  # 🔒 强制鉴权
        db: Session = Depends(get_sys_db)
):
    # ... (Agent 调用逻辑)
    result = agents["log"].analyze(request.log_content, request.session_id)

    # 💾 持久化保存
    save_chat_history(
        db,
        request.session_id,
        f"[日志分析] {request.log_content[:50]}...",  # 仅存摘要或完整存
        result["report"],
        current_user.id,
        "log"
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
