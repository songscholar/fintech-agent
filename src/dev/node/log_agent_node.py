import json
import re

from langchain_core.messages import HumanMessage, BaseMessage
from src.dev.moddleware.qa_moddleware import DynamicModelManager
from src.dev.retriever.konwage_retriever import KnowledgeRetriever
from src.dev.state.graph_state import LogGraphState
from src.dev.utils.log_parser import UniversalLogParser


def preprocess_and_parse(state: LogGraphState) -> LogGraphState:
    """节点1: 智能解析与类型识别"""
    print("🔍 [解析] 正在分析日志结构...")
    user_input = state["user_input"].strip()

    # 1. 优先调用确定性脚本解析 (正则/JSON提取)
    try:
        parsed_data = UniversalLogParser.parse(user_input)
    except Exception as e:
        print(f"⚠️ 解析器异常: {e}")
        parsed_data = {"success": False}

    # 2. 根据结果处理
    if parsed_data.get("success"):
        state["parsed_info"] = parsed_data
        state["log_type"] = parsed_data["log_type"]
        print(f"✅ 规则解析成功: [{state['log_type']}] ErrorCode={parsed_data['error_code']}")

        # 针对 Java 日志的特殊处理：尝试提取异常类名，辅助后续检索
        if state["log_type"] == "JAVA_ERROR_LOG":
            ex_match = re.search(r"([\w\.]+(?:Exception|Error))", user_input)
            if ex_match:
                state["parsed_info"]["exception_class"] = ex_match.group(1).split('.')[-1]
    else:
        # LLM 兜底逻辑
        print("⚠️ 规则解析未命中，降级使用通用模式...")
        state["parsed_info"] = {
            "log_type": "UNKNOWN",
            "summary": user_input[:200],
            "error_code": "UNKNOWN"
        }
        state["log_type"] = "UNKNOWN"

    return state


def expand_search_queries(state: LogGraphState) -> LogGraphState:
    """节点2: 查询扩展 (Query Expansion)"""
    print("🧠 [思考] 生成多维检索词...")
    parsed = state["parsed_info"]
    queries = []

    # 1. 核心报错信息
    if parsed.get("summary"):
        queries.append(parsed["summary"])

    # 2. 错误码精确搜索
    if parsed.get("error_code") and parsed["error_code"] not in ["N/A", "UNKNOWN"]:
        queries.append(f"错误码 {parsed['error_code']} 解决方案")

    # 3. 组件/源码级搜索 (这对 C++ BizLog 非常有效)
    if parsed.get("component") and parsed["component"] != "UNKNOWN":
        queries.append(f"{parsed['component']} error troubleshooting")

    # 4. Java 异常类搜索
    if parsed.get("exception_class"):
        queries.append(f"{parsed['exception_class']} cause and fix")

    # 去重并限制数量
    unique_queries = list(dict.fromkeys([q for q in queries if q]))
    state["search_queries"] = unique_queries[:3]
    print(f"✅ 生成查询词: {state['search_queries']}")
    return state


def retrieve_multi_source(state: LogGraphState) -> LogGraphState:
    """节点3: 并行/聚合检索"""
    print("🔎 [检索] 执行多路召回...")
    retriever = KnowledgeRetriever()
    results = []

    # 遍历查询词 (KnowledgeRetriever 内部已封装 "本地优先->联网兜底" 逻辑)
    for q in state["search_queries"]:
        if len(q) < 4: continue
        res = retriever.retrieve(q)
        if res and "无实际有效内容" not in res:
            results.append(f"【查询: {q}】\n{res[:800]}...")  # 限制长度防止 Context 爆炸

    state["retrieval_context"] = "\n\n".join(results) if results else "未检索到直接相关信息"
    return state


def generate_candidate_solution(state: LogGraphState) -> LogGraphState:
    """节点4: 生成候选方案"""
    print("📝 [生成] 编写诊断报告...")
    model = DynamicModelManager().get_model("gpt-4o")  # 建议用强模型

    prompt = f"""
    请作为高级技术专家，根据以下信息生成诊断报告。

    【日志概要】:
    类型: {state['log_type']}
    错误码: {state['parsed_info'].get('error_code')}
    摘要: {state['parsed_info'].get('summary')}

    【检索到的参考知识】: 
    {state['retrieval_context']}

    【任务要求】:
    1. 必须包含章节：🚨 根因分析、🛠️ 解决方案、💡 预防建议。
    2. 若参考知识中有明确案例，请引用。
    3. 若是 C++ 源码报错，请根据文件路径({state['parsed_info'].get('component')})推测模块功能。
    4. 输出格式为 Markdown。
    """

    response = model.invoke(prompt)
    state["candidate_answer"] = response.content
    return state


def evaluate_solution(state: LogGraphState) -> LogGraphState:
    """节点5: 自我评估 (Self-Reflection)"""
    print("⚖️ [评估] 审核回答质量...")
    if "retry_count" not in state: state["retry_count"] = 0

    prompt = f"""
    请评估以下技术回答的质量。
    回答内容: {state['candidate_answer']}

    标准:
    1. 是否给出了具体可执行的建议？(不仅仅是“联系管理员”)
    2. 是否逻辑通顺？

    输出JSON: {{"passed": true/false, "reason": "...", "score": 0-100}}
    """

    try:
        model = DynamicModelManager().get_model("default")
        res = model.invoke(prompt)
        content = res.content.strip()
        # 简单的 JSON 提取
        if "```" in content:
            content = re.search(r"\{.*\}", content, re.DOTALL).group()
        eval_result = json.loads(content)
    except:
        eval_result = {"passed": True, "score": 60}  # 兜底通过

    state["evaluation_result"] = eval_result
    print(f"✅ 评分: {eval_result.get('score')} ({'通过' if eval_result.get('passed') else '需修改'})")
    return state


def rewrite_solution(state: LogGraphState) -> LogGraphState:
    """节点6: 修正重写"""
    print("🔄 [修正] 优化回答...")
    state["retry_count"] += 1
    reason = state["evaluation_result"].get("reason", "补充更多细节")

    model = DynamicModelManager().get_model("gpt-4o")
    prompt = f"""
    原回答未通过审核，原因: {reason}。
    请基于原有信息重写，使其更具操作性。

    原回答: {state['candidate_answer']}
    """
    response = model.invoke(prompt)
    state["candidate_answer"] = response.content
    return state


def finalize_output(state: LogGraphState) -> LogGraphState:
    """节点7: 最终交付"""
    state["final_answer"] = state["candidate_answer"]
    state["messages"] = [
        HumanMessage(content=state["user_input"]),
        BaseMessage(content=state["final_answer"], type="assistant")
    ]
    return state


# --- 条件边逻辑 ---
def check_evaluation(state: LogGraphState):
    if state["evaluation_result"].get("passed", False):
        return "approved"
    if state["retry_count"] >= state.get("max_retries", 1):
        return "max_retries"
    return "rewrite"