from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langgraph.channels import LastValue
from langgraph.graph.message import add_messages


# ============== 基础类型定义 ==============
class QAGraphState(TypedDict):
    """定义流程图的状态"""
    messages: Annotated[List[BaseMessage], add_messages]
    user_input: Annotated[Optional[str], LastValue(str)]
    question_type: Optional[str]  # "business" or "general"
    context: Optional[str]
    file_content: Optional[str]
    url_content: Optional[str]
    processed_input: Optional[str]
    retrieval_result: Optional[str]
    answer: Optional[str]
    answer_validated: Optional[bool]
    session_id: str
    metadata: Dict[str, Any]
    retry_count: int
    skip_subsequent: bool
    question_compliance: Annotated[Optional[str], LastValue(str)]

@dataclass()
class DatabaseGraphState:
    """数据库智能体状态类"""
    # 用户输入相关
    user_input: str = ""
    session_id: str = ""
    messages: List[Dict[str, Any]] = None

    # 数据库相关
    db_connection_string: str = ""
    db_metadata: Dict[str, Any] = None
    selected_tables: List[str] = None
    db_type = None

    # SQL相关
    sql_query: str = ""
    sql_type: str = ""  # SELECT, INSERT, UPDATE, DELETE, DDL
    sql_validation_result: Dict[str, Any] = None
    sql_execution_result: Any = None
    sql_error: str = ""

    # 流程控制
    requires_human_approval: bool = False
    human_approved: bool = False
    retry_count: int = 0
    max_retries: int = 3

    # 中间结果
    parsed_intent: Dict[str, Any] = None
    generated_sql: str = ""
    validated_sql: str = ""
    execution_plan: List[Dict[str, Any]] = None

    # 输出相关
    final_answer: str = ""
    visualization_data: Dict[str, Any] = None

    def __post_init__(self):
        if self.messages is None:
            self.messages = []
        if self.db_metadata is None:
            self.db_metadata = {}
        if self.selected_tables is None:
            self.selected_tables = []
        if self.sql_validation_result is None:
            self.sql_validation_result = {}
        if self.execution_plan is None:
            self.execution_plan = []

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)

    def update(self, **kwargs):
        """更新状态"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)