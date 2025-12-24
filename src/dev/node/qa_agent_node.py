import copy
import re
from datetime import datetime

from langchain_core.messages import HumanMessage, BaseMessage

from src.dev.common.constant import MAX_RETRY_COUNT
from src.dev.log.common_log import log_node_execution
from src.dev.memory.qa_agent_memory import MemoryManager
from src.dev.moddleware.qa_moddleware import DynamicModelManager
from src.dev.prompt.qa_prompt import QAPromptManager
from src.dev.retriever.konwage_retriever import KnowledgeRetriever
from src.dev.state.graph_state import GraphState
from src.dev.utils.scholar_tools import fetch_url_content, extract_file_content

def preprocess(state: GraphState) -> GraphState:
    """1. 前置处理：提取URL和文件信息"""
    user_input = state["user_input"]
    print(f"🚀 开始处理用户输入: {user_input[:50]}...")

    # 提取URL
    url_pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w\.-]*'
    urls = re.findall(url_pattern, user_input)

    if urls:
        print(f"🔗 检测到URL: {urls}")
        # 清理输入中的URL
        for url in urls:
            user_input = user_input.replace(url, "").strip()
        state["url_content"] = "\n".join([fetch_url_content(url) for url in urls])

    # 检查文件路径（简化处理，实际中需要文件上传机制）
    file_pattern = r'(\.pdf|\.txt|\.docx?)$'
    if re.search(file_pattern, user_input, re.IGNORECASE):
        print("📄 检测到文件引用")
        state["file_content"] = extract_file_content(user_input)

    state["processed_input"] = user_input
    return state


def check_sensitive_question(state: GraphState) -> GraphState:
    state = copy.deepcopy(state)

    # 1. 合规校验Prompt（金融场景定制，语义级判断）
    compliance_prompt = QAPromptManager().get_prompt(
        "compliance",
        context="",
        question=state["processed_input"]
    )

    # 2. 小模型调用（轻量、快速）
    try:
        compliance_model = DynamicModelManager().get_model("deepseek")
        response = compliance_model.invoke([{"role": "user", "content": compliance_prompt}])
        state["question_compliance"] = response.content.strip()

        # 3. 违规则生成提示语（合规则无操作）
        if state["question_compliance"] == "违规":
            state["answer"] = (
                "您的问题涉及金融违规相关内容，根据监管要求，无法为您解答。\n"
                "【合规提示】：请遵守《证券法》《商业银行法》等相关法规，咨询合法合规的金融问题。"
            )
            state["skip_subsequent"] = True  # 标记跳过后续流程
    except Exception as e:
        # 容错：小模型调用失败时，降级为关键词校验（兜底）
        forbidden_keywords = ["内幕交易", "保本保收益", "代客理财", "洗钱", "非法集资"]
        if any(k in state["processed_question"] for k in forbidden_keywords):
            state["question_compliance"] = "违规"
            state["answer"] = "您的问题涉及违规内容，无法解答。"
            state["skip_subsequent"] = True
        else:
            state["question_compliance"] = "合规"

    return state

def type_classification(state: GraphState) -> GraphState:
    """1.4. 类型识别：判断是业务问题还是普通问题"""
    print("🔍 进行问题类型识别...")

    prompt_manager = QAPromptManager()
    model_manager = DynamicModelManager()

    prompt = prompt_manager.get_prompt(
        "type_classification",
        question=state["processed_input"]
    )

    model = model_manager.get_model()
    response = model.invoke(prompt)

    question_type = response.content.strip().lower()
    if "business" in question_type:
        state["question_type"] = "business"
    else:
        state["question_type"] = "general"

    print(f"📊 识别结果: {state['question_type']}")
    return state

def summarize_input(state: GraphState) -> GraphState:
    """1.3. 总结信息获取用户问题"""
    print("📝 总结用户问题...")

    # 合并所有信息源
    context_parts = []
    if state.get("url_content"):
        context_parts.append(f"URL内容：{state['url_content']}")
    if state.get("file_content"):
        context_parts.append(f"文件内容：{state['file_content']}")

    if context_parts:
        summary_context = "\n".join(context_parts)

        # 使用模型总结
        model = DynamicModelManager().get_model()
        summary_prompt = f"""
        请总结以下信息，帮助理解用户的核心问题：

        信息：
        {summary_context}

        用户原始问题：
        {state['processed_input']}

        请用一句话总结用户的核心关切：
        """

        response = model.invoke(summary_prompt)
        state["context"] = response.content
    else:
        state["context"] = state["processed_input"]

    print(f"✅ 总结完成: {state['context'][:100]}...")
    return state


@log_node_execution
def retrieve_context(state: GraphState) -> GraphState:
    """2.1.1/通用检索：根据用户问题检索上下文"""
    print("🔎 检索相关知识...")

    retriever = KnowledgeRetriever()

    # 构建查询
    query = state["context"]
    if state.get("question_type") == "business":
        query = f"金融业务: {query}"

    # 检索
    retrieved = retriever.retrieve(query)

    if retrieved:
        state["retrieval_result"] = retrieved
        print(f"✅ 检索到 {len(retrieved.split())} 个词的上下文")
    else:
        state["retrieval_result"] = ""
        print("⚠️  未检索到相关上下文")

    return state


# ============== 8. 业务回答节点 ==============
@log_node_execution
def answer_business_question(state: GraphState) -> GraphState:

    try:
        """2.1. 回答客户业务信息"""
        print("🏦 生成业务问题回答...")

        prompt_manager = QAPromptManager()
        model_manager = DynamicModelManager()

        # 准备上下文
        context = ""
        if state.get("retrieval_result"):
            context += f"知识库信息：\n{state['retrieval_result']}\n\n"
        if state.get("context"):
            context += f"问题总结：\n{state['context']}"

        # 获取动态提示词
        prompt = prompt_manager.get_prompt(
            "business",
            context=context,
            question=state["processed_input"]
        )

        # 选择模型 todo 搞一个金融模型模型
        model = model_manager.get_model("default")

        # 生成回答
        response = model.invoke(prompt)
        state["answer"] = response.content

        print(f"✅ 业务回答生成完成，长度: {len(state['answer'])} 字符")
    except Exception as e:
        # 降级策略：使用兜底模型/提示语
        state["answer"] = f"回答生成失败（原因：{str(e)}），请稍后重试。"
        state["answer_validated"] = False

    return state

# ============== 9. 普通回答节点 ==============
@log_node_execution
def answer_general_question(state: GraphState) -> GraphState:
    """2.2. 回答客户普通问题"""
    print("💬 生成普通问题回答...")

    prompt_manager = QAPromptManager()
    model_manager = DynamicModelManager()

    # 准备上下文
    context = ""
    if state.get("retrieval_result"):
        context += f"相关知识：\n{state['retrieval_result']}\n\n"
    if state.get("context"):
        context += f"问题背景：\n{state['context']}"

    # 获取动态提示词
    prompt = prompt_manager.get_prompt(
        "general",
        context=context,
        question=state["processed_input"]
    )

    # 选择模型 todo 搞一个通用模型模型
    model = model_manager.get_model("deepseek")

    # 生成回答
    response = model.invoke(prompt)
    state["answer"] = response.content

    print(f"✅ 普通回答生成完成，长度: {len(state['answer'])} 字符")
    return state


# ============== 10. 答案校验节点 ==============
def validate_answer(state: GraphState) -> GraphState:
    """2.3. 校验答案"""
    print("✅ 校验答案质量...")

    prompt_manager = QAPromptManager()
    model_manager = DynamicModelManager()

    prompt = prompt_manager.get_prompt(
        "validation",
        question=state["processed_input"],
        answer=state["answer"]
    )

    model = model_manager.get_model()
    response = model.invoke(prompt)

    validation_result = response.content.strip()

    if "通过" in validation_result:
        state["answer_validated"] = True
        print("🎉 答案验证通过")
    else:
        state["answer_validated"] = False
        # 校验不通过重试次数+1，
        state["retry_count"] += 1
        print("⚠️  答案验证不通过，需要重新生成")

    return state


# ============== 11. 后置处理节点 ==============
def postprocess_output(state: GraphState) -> GraphState:
    """3. END: 后置处理"""
    print("🔧 进行后置处理...")

    # 添加回答到消息历史
    state["messages"].append(HumanMessage(content=state["user_input"]))
    state["messages"].append(
        BaseMessage(content=state["answer"], type="assistant")
    )

    # 保存到记忆
    memory_manager = MemoryManager()
    memory_manager.save_memory(
        state["session_id"],
        {
            "timestamp": datetime.now().isoformat(),
            "user_input": state["user_input"],
            "answer": state["answer"],
            "question_type": state["question_type"],
            "validated": state["answer_validated"]
        }
    )

    # 清理临时状态
    state["user_input"] = ""

    print("✅ 后置处理完成")
    return state

# 异常处理
def handle_retrieve_empty(state: GraphState) -> GraphState:
    state = copy.deepcopy(state)
    # 金融场景友好提示（避免生硬，同时加合规说明）
    state["answer"] = (
        "很抱歉，未检索到与该业务问题相关的有效信息，无法为您解答。\n"
        "【温馨提示】：您可尝试调整问题表述（如补充具体金融产品/业务场景），或咨询相关金融机构的专业人员。\n"
        "【风险提示】：本回复仅为信息参考，不构成任何投资建议。"
    )
    state["final_answer"] = state["answer"]  # 直接赋值最终回答，跳过后续postprocess的冗余处理
    return state

# 条件判断
def validate_branch(state: GraphState):
    # 校验通过 → 后处理
    if state["answer_validated"]:
        return "validated"
    # 校验不通过：重试次数未到 → 重新检索/回答；次数到 → 终止
    elif state["retry_count"] < MAX_RETRY_COUNT:
        # 业务问题重新检索，通用问题重新回答
        return "retry_" + state["question_type"]
    else:
        return "max_retry"

def retrieve_branch(state: GraphState):
    # 判定“无有效信息”的条件：
    # - 检索结果为空 / 长度过短（<50个字，排除无意义碎片）
    if not state.get("retrieval_result") or len(state["retrieval_result"].strip()) < 50:
        return "empty"
    return "normal"