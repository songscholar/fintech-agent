import os
import warnings
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_tavily import TavilySearch  # 新版导入
from langchain_core.documents import Document

# 加载环境变量
load_dotenv()

# 抑制Tavily内部的stream字段警告
warnings.filterwarnings("ignore", category=UserWarning, message="Field name \"stream\" in \"TavilyResearch\"")

class KnowledgeRetriever:
    """增强版知识检索器：优先本地知识库，本地无结果则联网检索"""

    def __init__(self, vector_store_path: str = "./chroma_db", k: int = 3):
        self.embeddings = OpenAIEmbeddings()
        self.vector_store_path = vector_store_path
        self.k = k
        self.vector_store = self._init_vector_store()

        # 验证并加载Tavily API Key
        tavily_api_key = os.getenv("TAVILY_API_KEY")
        if not tavily_api_key:
            raise ValueError("⚠️  未配置TAVILY_API_KEY，请在.env文件中添加")

        # 初始化新版TavilySearch（显式传API Key）
        self.web_retriever = TavilySearch(
            api_key=tavily_api_key,
            max_results=self.k,
            search_depth="basic",
            include_raw_content=True,
            include_images=False
        )

    def _init_vector_store(self) -> Chroma:
        """初始化本地向量存储"""
        try:
            vector_store = Chroma(
                persist_directory=self.vector_store_path,
                embedding_function=self.embeddings
            )
            if vector_store._collection.count() == 0:
                return self._create_empty_vector_store()
            return vector_store
        except Exception as e:
            print(f"加载本地向量库失败，创建新库: {e}")
            return self._create_empty_vector_store()

    def _create_empty_vector_store(self) -> Chroma:
        """创建空向量库"""
        return Chroma.from_texts(
            texts=["金融知识库初始化占位符，无实际有效内容"],
            embedding=self.embeddings,
            persist_directory=self.vector_store_path
        )

    def _is_local_result_valid(self, local_docs: list[Document]) -> bool:
        """判断本地检索结果是否有效"""
        if not local_docs:
            return False
        placeholder = "金融知识库初始化占位符，无实际有效内容"
        for doc in local_docs:
            if doc.page_content.strip() != placeholder:
                return True
        return False

    def _local_retrieve(self, query: str) -> str:
        """本地知识库检索"""
        try:
            docs = self.vector_store.similarity_search(query, k=self.k)
            if self._is_local_result_valid(docs):
                local_content = "\n\n".join([f"【本地知识库】{doc.page_content}" for doc in docs])
                print("✅ 本地知识库检索到有效结果")
                return local_content
            print("⚠️  本地知识库无有效结果，准备联网检索")
            return ""
        except Exception as e:
            print(f"本地检索失败: {e}")
            return ""

    def _web_retrieve(self, query: str) -> str:
        """联网检索（兼容 Tavily 所有返回格式：str/list/dict）"""
        try:
            search_results = self.web_retriever.invoke(query)
            print(f"📌 Tavily返回类型: {type(search_results)}")  # 调试用，可保留

            # 情况1：返回嵌套字典（新版默认，含results字段）
            if isinstance(search_results, dict):
                # 提取核心结果列表（优先取results字段）
                results_list = search_results.get("results", [])
                if not results_list:
                    # 兜底：取整个字典的文本内容（避免空结果）
                    raw_text = str(search_results)
                    return f"【联网结果】{raw_text[:1000]}" if raw_text else ""

                # 解析results列表（和之前的列表逻辑一致）
                web_content = []
                for idx, result in enumerate(results_list, 1):
                    if isinstance(result, dict):
                        title = result.get("title", "无标题")
                        url = result.get("url", "")
                        content = result.get("content", result.get("raw_content", "")).strip()
                        if content:
                            web_content.append(
                                f"【联网结果-{idx}】\n标题：{title}\n链接：{url}\n内容：{content[:500]}"
                            )
                    elif isinstance(result, str) and result.strip():
                        web_content.append(f"【联网结果-{idx}】\n{result[:500]}")
                return "\n\n".join(web_content) if web_content else ""

            # 情况2：返回纯字符串（基础搜索）
            elif isinstance(search_results, str):
                search_results = search_results.strip()
                return f"【联网结果】\n{search_results[:1000]}" if search_results else ""

            # 情况3：返回列表（旧版结构化结果）
            elif isinstance(search_results, list):
                web_content = []
                for idx, result in enumerate(search_results, 1):
                    if isinstance(result, dict):
                        title = result.get("title", "无标题")
                        url = result.get("url", "")
                        content = result.get("content", result.get("raw_content", "")).strip()
                        if content:
                            web_content.append(
                                f"【联网结果-{idx}】\n标题：{title}\n链接：{url}\n内容：{content[:500]}"
                            )
                    elif isinstance(result, str) and result.strip():
                        web_content.append(f"【联网结果-{idx}】\n{result[:500]}")
                return "\n\n".join(web_content) if web_content else ""

            # 未知类型兜底
            else:
                print(f"⚠️  不支持的返回格式: {type(search_results)}")
                return ""

        except Exception as e:
            print(f"联网检索失败: {e}")
            # 可选：打印完整报错栈，方便定位
            # import traceback
            # traceback.print_exc()
            return ""

    def retrieve(self, query: str) -> str:
        """主检索方法"""
        # 1. 优先本地检索
        local_result = self._local_retrieve(query)
        if local_result:
            return local_result

        # 2. 本地无结果则联网检索
        web_result = self._web_retrieve(query)
        if web_result:
            return web_result

        # 3. 兜底提示
        return "⚠️  本地知识库和互联网均未检索到相关信息，请调整问题表述或补充知识库内容。"