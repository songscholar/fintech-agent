import re
from datetime import datetime

from langchain_core.messages import HumanMessage, BaseMessage

from src.dev.memory.qa_agent_memory import MemoryManager
from src.dev.moddleware.qa_moddleware import DynamicModelManager
from src.dev.prompt.qa_prompt import QAPromptManager
from src.dev.retriever.konwage_retriever import KnowledgeRetriever
from src.dev.state.graph_state import GraphState
from src.dev.utils.scholar_tools import fetch_url_content, extract_file_content


def preprocess_node(state: GraphState) -> GraphState:
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

def type_classification_node(state: GraphState) -> GraphState:
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

def summarize_input_node(state: GraphState) -> GraphState:
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



def retrieve_context_node(state: GraphState) -> GraphState:
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
def answer_business_question_node(state: GraphState) -> GraphState:
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

    # 选择模型
    model = model_manager.select_model_based_on_type("business")

    # 生成回答
    response = model.invoke(prompt)
    state["answer"] = response.content

    print(f"✅ 业务回答生成完成，长度: {len(state['answer'])} 字符")
    return state



# ============== 9. 普通回答节点 ==============
def answer_general_question_node(state: GraphState) -> GraphState:
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

    # 选择模型
    model = model_manager.select_model_based_on_type("general")

    # 生成回答
    response = model.invoke(prompt)
    state["answer"] = response.content

    print(f"✅ 普通回答生成完成，长度: {len(state['answer'])} 字符")
    return state


# ============== 10. 答案校验节点 ==============
def validate_answer_node(state: GraphState) -> GraphState:
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
        print("⚠️  答案验证不通过，需要重新生成")

    return state


# ============== 11. 后置处理节点 ==============
def postprocess_output_node(state: GraphState) -> GraphState:
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