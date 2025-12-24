from typing import Any, Dict, List, Optional, TypedDict, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


# ============== 基础类型定义 ==============
class GraphState(TypedDict):
    """定义流程图的状态"""
    messages: Annotated[List[BaseMessage], add_messages]
    user_input: str
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