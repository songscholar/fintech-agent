import os

from langchain_core.messages import BaseMessage
from langgraph.store.memory import InMemoryStore
from langchain.messages import HumanMessage
from langgraph.graph import StateGraph, END

from src.dev.node.qa_agent_node import preprocess_node, summarize_input_node, type_classification_node, \
    retrieve_context_node, answer_business_question_node, answer_general_question_node, validate_answer_node, \
    postprocess_output_node
from src.dev.state.graph_state import GraphState
import src.dev.utils.scholar_tools as tools
from src.dev.memory.qa_agent_memory import MemoryManager
from src.dev.prompt.qa_prompt import QAPromptManager
from src.dev.moddleware.qa_moddleware import DynamicModelManager

def build_financial_agent():
    """构建金融问答智能体流程图"""

    # 创建状态图
    workflow = StateGraph(GraphState)

    # 添加节点
    workflow.add_node("preprocess", preprocess_node)  # 1.1 & 1.2
    workflow.add_node("summarize", summarize_input_node)  # 1.3
    workflow.add_node("classify", type_classification_node)  # 1.4
    workflow.add_node("retrieve", retrieve_context_node)  # 2.1.1
    workflow.add_node("answer_business", answer_business_question_node)  # 2.1
    workflow.add_node("answer_general", answer_general_question_node)  # 2.2
    workflow.add_node("validate", validate_answer_node())  # 2.3
    workflow.add_node("postprocess", postprocess_output_node())  # 3.END

    # 设置入口点
    workflow.set_entry_point("preprocess")

    # 添加边（根据流程图）
    workflow.add_edge("preprocess", "summarize")
    workflow.add_edge("summarize", "classify")

    # 类型识别后的分支
    workflow.add_conditional_edges(
        "classify",
        lambda state: state["question_type"],
        {
            "business": "retrieve",
            "general": "retrieve"
        }
    )

    # 检索后的分支
    workflow.add_conditional_edges(
        "retrieve",
        lambda state: state["question_type"],
        {
            "business": "answer_business",
            "general": "answer_general"
        }
    )

    # 回答后校验
    workflow.add_edge("answer_business", "validate")
    workflow.add_edge("answer_general", "validate")

    # 校验结果分支
    workflow.add_conditional_edges(
        "validate",
        lambda state: "answer_validated" if state.get("answer_validated") else "not_validated",
        {
            "answer_validated": "postprocess",
            "not_validated": "retrieve"  # 不通过则重新检索生成
        }
    )

    # 结束
    workflow.add_edge("postprocess", END)

    # 编译图
    memory = InMemoryStore()
    app = workflow.compile(checkpointer=memory)

    return app

# ============== 14. 使用示例 ==============
class FinancialQAAssistant:
    """金融问答助手主类"""

    def __init__(self):
        self.app = build_financial_agent()
        self.memory_manager = MemoryManager()
        self.prompt_manager = QAPromptManager()
        self.model_manager = DynamicModelManager()

    def ask(self, question: str, session_id: str = None):
        """提问入口"""

        # 生成或使用会话ID
        if not session_id:
            session_id = tools.generate_session_id(question)

        print(f"\n{'=' * 50}")
        print(f"会话: {session_id}")
        print(f"问题: {question}")
        print(f"{'=' * 50}\n")

        # 加载历史记忆
        memory_history = self.memory_manager.load_memory(session_id)
        initial_messages = []

        # 添加历史上下文（最后3轮）
        for mem in memory_history[-3:]:
            initial_messages.append(HumanMessage(content=mem.get("user_input", "")))
            initial_messages.append(BaseMessage(content=mem.get("answer", ""), type="assistant"))

        # 准备初始状态
        initial_state = {
            "messages": initial_messages,
            "user_input": question,
            "question_type": None,
            "context": None,
            "file_content": None,
            "url_content": None,
            "processed_input": None,
            "retrieval_result": None,
            "answer": None,
            "answer_validated": None,
            "session_id": session_id,
            "metadata": {}
        }

        # 执行流程图
        config = {"configurable": {"thread_id": session_id}}
        result = self.app.invoke(initial_state, config)

        # 返回结果
        return {
            "answer": result["answer"],
            "session_id": session_id,
            "question_type": result["question_type"],
            "validated": result["answer_validated"],
            "context_used": bool(result.get("retrieval_result"))
        }

    def get_session_history(self, session_id: str):
        """获取会话历史"""
        return self.memory_manager.load_memory(session_id)


# ============== 15. 测试函数 ==============
def test_financial_assistant():
    """测试金融问答助手"""

    print("🧪 测试金融问答智能体...")

    assistant = FinancialQAAssistant()

    # 测试用例
    test_cases = [
        "什么是定期存款？",  # 业务问题
        "帮我解释一下股票投资的风险",  # 业务问题
        "今天的天气怎么样？",  # 普通问题
        "https://www.example.com 这个网站的金融产品如何？",  # 包含URL
        "投资理财有什么建议？",  # 业务问题
    ]

    session_id = "test_session_001"

    for i, question in enumerate(test_cases, 1):
        print(f"\n📋 测试用例 {i}: {question}")

        try:
            result = assistant.ask(question, session_id)

            print(f"📤 回答类型: {result['question_type']}")
            print(f"✅ 验证状态: {result['validated']}")
            print(f"📝 回答摘要: {result['answer'][:150]}...")
            print("-" * 50)

        except Exception as e:
            print(f"❌ 处理失败: {e}")
            import traceback
            traceback.print_exc()


# ============== 16. 主函数 ==============
if __name__ == "__main__":
    # 设置API密钥
    os.environ["OPENAI_API_KEY"] = "your-api-key-here"  # 请替换为您的API密钥

    # 运行测试
    test_financial_assistant()

    # 或者创建实例使用
    # assistant = FinancialQAAssistant()
    # result = assistant.ask("什么是投资基金？")
    # print(result["answer"])
