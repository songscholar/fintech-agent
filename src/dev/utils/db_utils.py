# src/dev/common/db_utils.py
from sqlalchemy import  engine
from typing import Optional, Dict
from dataclasses import dataclass, field
from src.dev.database.db_connection_manager import DatabaseConnectionManager

# 1. 抽离状态类（如果 sql_agent_node.py 也依赖 DatabaseGraphState）
@dataclass
class DatabaseGraphState:
    user_input: str
    session_id: str
    db_connection_string: Optional[str] = None
    messages: list = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 3
    # ... 其他字段（保持和原来一致）

# 2. 抽离 Engine 获取逻辑（避免依赖 DatabaseAgent）
class DBEngineProvider:
    _instance = None  # 单例模式，确保只创建一个 Engine
    _engine = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def init_engine(self, conn_str: str):
        """初始化 Engine（只执行一次）"""
        if not self._engine:
            db_manager = DatabaseConnectionManager()
            self._engine = db_manager.create_connection(conn_str, alias="primary")
        return self._engine

    def get_engine(self) -> Optional[engine.Engine]:
        """获取已初始化的 Engine"""
        return self._engine

# 全局单例，供所有模块使用
engine_provider = DBEngineProvider()