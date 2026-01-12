from typing import Dict, Any

from langgraph.graph import StateGraph, END
from langgraph.constants import START
from langgraph.checkpoint.memory import InMemorySaver

# 导入节点和状态
from src.dev.node.log_agent_node import (
    preprocess_and_parse,
    expand_search_queries,
    retrieve_multi_source,
    generate_candidate_solution,
    evaluate_solution,
    rewrite_solution,
    finalize_output,
    check_evaluation
)
from src.dev.state.graph_state import LogGraphState
from src.dev.utils.scholar_tools import generate_session_id


def build_enterprise_log_agent():
    """构建企业级日志分析智能体"""
    print("🏗️  构建日志智能体 (v2.0)...")

    workflow = StateGraph(LogGraphState)

    # 1. 注册节点
    workflow.add_node("preprocess", preprocess_and_parse)
    workflow.add_node("expand_query", expand_search_queries)
    workflow.add_node("retrieve", retrieve_multi_source)
    workflow.add_node("generate", generate_candidate_solution)
    workflow.add_node("evaluate", evaluate_solution)
    workflow.add_node("rewrite", rewrite_solution)
    workflow.add_node("finalize", finalize_output)

    # 2. 定义主流程
    workflow.add_edge(START, "preprocess")
    workflow.add_edge("preprocess", "expand_query")
    workflow.add_edge("expand_query", "retrieve")
    workflow.add_edge("retrieve", "generate")
    workflow.add_edge("generate", "evaluate")

    # 3. 定义反思闭环
    workflow.add_conditional_edges(
        "evaluate",
        check_evaluation,
        {
            "approved": "finalize",  # 质量达标 -> 结束
            "rewrite": "rewrite",  # 不达标 -> 重写
            "max_retries": "finalize"  # 超过重试 -> 强制结束
        }
    )
    workflow.add_edge("rewrite", "evaluate")  # 重写后再次评估
    workflow.add_edge("finalize", END)

    return workflow.compile(checkpointer=InMemorySaver())


class LogAnalysisAgent:
    """日志分析助手对外接口类"""

    def __init__(self):
        self.app = build_enterprise_log_agent()

    def analyze(self, log_content: str, session_id: str = None) -> Dict[str, Any]:
        """执行分析任务"""
        if not session_id:
            session_id = generate_session_id(log_content)

        print(f"\n🚀 [Start] Log Analysis Session: {session_id}")

        initial_state = {
            "session_id": session_id,
            "user_input": log_content,
            "max_retries": 1,  # 允许自我修正1次
            "retry_count": 0,
            "messages": []
        }

        config = {"configurable": {"thread_id": session_id}}

        try:
            result = self.app.invoke(initial_state, config)
            return {
                "success": True,
                "report": result["final_answer"],
                "log_type": result.get("log_type"),
                "parsed_data": result.get("parsed_info"),
                "session_id": session_id
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}


# --- 测试入口 ---
if __name__ == "__main__":
    agent = LogAnalysisAgent()

    # 测试 Java 日志
    java_log = """2026-01-08 16:20:00.012 |-ERROR [Thread-1] [] [] com.hundsun.log [] -|{"type":"4","myPackage":{"error_no":"99998","error_info":"DB Error"}}
    java.sql.SQLTransientConnectionException: Connection is not available"""

    print("\n---------------- Processing Java Log ----------------")
    res = agent.analyze(java_log)
    print(f"\n[Result] Type: {res['log_type']}\nReport:\n{res['report']}...")


# if __name__ == "__main__":
#     """构建金融问答智能体流程图"""
#
#     app = build_enterprise_log_agent()
#
#     png_data = app.get_graph().draw_mermaid_png()
#     with open('graph.png', 'wb') as f:
#         f.write(png_data)
#     print("图像已保存为graph.png")
#     # 可以尝试自动打开文件
#     import webbrowser, os
#
#     webbrowser.open('file://' + os.path.realpath('graph.png'))