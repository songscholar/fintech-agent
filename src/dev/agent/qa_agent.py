import os

from langchain.agents.middleware import HumanInTheLoopMiddleware, SummarizationMiddleware, PIIMiddleware
from langchain_core.messages import HumanMessage, BaseMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.constants import START
from langgraph.graph import StateGraph, END
from langgraph.store.memory import InMemoryStore

from src.dev.memory.qa_agent_memory import MemoryManager
from src.dev.node.qa_agent_node import preprocess, summarize_input, type_classification, retrieve_context, \
    answer_business_question, answer_general_question, validate_answer, postprocess_output, handle_retrieve_empty, \
    validate_branch, retrieve_branch, check_sensitive_question
from src.dev.state.graph_state import GraphState
from src.dev.utils.scholar_tools import generate_session_id


def build_financial_agent():
    """构建金融问答智能体流程图"""

    # 创建状态图
    workflow = StateGraph(GraphState)

    # 2. 添加节点（职责不变，仅调整顺序）
    workflow.add_node("preprocess", preprocess)  # 1.1 预处理问题
    workflow.add_node("check_sensitive_question", check_sensitive_question)  # 用户问题合规性检查
    workflow.add_node("summarize", summarize_input)  # 1.2 总结问题
    workflow.add_node("classify", type_classification)  # 1.3 分类问题类型
    workflow.add_node("retrieve", retrieve_context)  # 1.4 检索业务上下文
    workflow.add_node("answer_business", answer_business_question)  # 2.1 回答业务问题（需检索）
    workflow.add_node("answer_general", answer_general_question)  # 2.2 回答通用问题（无需检索）
    workflow.add_node("validate", validate_answer)  # 2.3 校验回答
    workflow.add_node("postprocess", postprocess_output)  # 3. 后处理输出

    workflow.add_node("handle_retrieve_empty", handle_retrieve_empty)

    # 入口 → 预处理 → 总结 → 分类
    workflow.add_edge(START, "preprocess")
    workflow.add_edge("preprocess", "check_sensitive_question")
    workflow.add_edge("summarize", "classify")

    # 3. 合规校验后的分支：违规则直接到postprocess/END，合规则继续过滤无效问题
    workflow.add_conditional_edges(
        "check_sensitive_question",
        lambda s: "skip" if s.get("skip_subsequent") else "continue",
        {
            "skip": "postprocess",  # 违规问题直接走后处理（或直接到END）
            "continue": "summarize"  # 合规问题继续往下面执行
        }
    )

    # 分类后分支：business→检索→回答；general→直接回答
    workflow.add_conditional_edges(
        "classify",
        lambda state: state["question_type"],  # 基于分类结果分支
        {
            "business": "retrieve",  # 业务问题先检索
            "general": "answer_general"  # 通用问题直接回答
        }
    )

    workflow.add_conditional_edges(
        "retrieve",
        retrieve_branch,
        {
            "empty": "handle_retrieve_empty",  # 检索为空 → 处理节点
            "normal": "answer_business"  # 检索正常 → 继续原流程
        }
    )

    # 检索后直接回答业务问题（无需再判断类型）
    # workflow.add_edge("retrieve", "answer_business")

    # 回答后统一校验
    workflow.add_edge("answer_business", "validate")
    workflow.add_edge("answer_general", "validate")

    workflow.add_conditional_edges(
        "validate",
        validate_branch,
        {
            "validated": "postprocess",  # 校验通过
            "retry_business": "retrieve",  # 业务问题重试：重新检索
            "retry_general": "answer_general",  # 通用问题重试：重新回答
            "max_retry": END  # 重试次数用尽，终止流程
        }
    )

    # 后处理→结束
    workflow.add_edge("handle_retrieve_empty", END)
    workflow.add_edge("postprocess", END)

    # 编译图
    store = InMemoryStore()
    check_point = InMemorySaver()

    app = workflow.compile(store=store, checkpointer=check_point).with_config(
        middleware=[HumanInTheLoopMiddleware, SummarizationMiddleware, PIIMiddleware])

    return app


class FinancialQAAssistant:
    """金融问答助手主类"""

    def __init__(self):
        self.app = build_financial_agent()

    def ask(self, question: str, session_id: str = None):
        """提问入口"""

        # 生成或使用会话ID
        if not session_id:
            session_id = generate_session_id(question)

        print(f"\n{'=' * 50}")
        print(f"会话: {session_id}")
        print(f"问题: {question}")
        print(f"{'=' * 50}\n")

        memory_manager = MemoryManager()
        # 加载历史记忆
        memory_history = memory_manager.load_memory(session_id)
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
            "metadata": {},
            "retry_count": 0,
            "skip_subsequent": False,
            "question_compliance": None
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


# ============== 15. 测试函数 ==============
def test_financial_assistant():
    """测试金融问答助手"""

    print("🧪 测试金融问答智能体...")

    assistant = FinancialQAAssistant()

    # 测试用例
    # test_cases = [
    #     "什么是定期存款？",  # 业务问题
    #     "帮我解释一下股票投资的风险",  # 业务问题
    #     "今天的天气怎么样？",  # 普通问题
    #     "https://www.example.com 这个网站的金融产品如何？",  # 包含URL
    #     "投资理财有什么建议？",  # 业务问题
    # ]
    test_cases = [
        "什么是ETF业务？",  # 业务问题
    ]

    session_id = "test_session_001"

    for i, question in enumerate(test_cases, 1):
        print(f"\n📋 测试用例 {i}: {question}")

        try:
            result = assistant.ask(question, session_id)

            print(f"📤 回答类型: {result['question_type']}")
            print(f"✅ 验证状态: {result['validated']}")
            print(f"📝 回答摘要: {result['answer']}...")
            print("-" * 50)

        except Exception as e:
            print(f"❌ 处理失败: {e}")
            import traceback
            traceback.print_exc()


# ============== 16. 主函数 ==============
if __name__ == "__main__":
    # 设置API密钥
    os.environ["OPENAI_API_KEY"] = ""  # 请替换为您的API密钥
    os.environ["USER_AGENT"] = "fintech-agent/1.0 (songzuoqiang@gmail.com)"

    # 运行测试
    test_financial_assistant()

# see graph structure
# if __name__ == "__main__":
#     """构建金融问答智能体流程图"""
#
#     app = build_financial_agent()
#
#     png_data = app.get_graph().draw_mermaid_png()
#     with open('graph.png', 'wb') as f:
#         f.write(png_data)
#     print("图像已保存为graph.png")
#     # 可以尝试自动打开文件
#     import webbrowser, os
#
#     webbrowser.open('file://' + os.path.realpath('graph.png'))
