from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings


class KnowledgeRetriever:
    """知识检索器"""

    def __init__(self, vector_store_path: str = "./chroma_db"):
        self.embeddings = OpenAIEmbeddings()
        self.vector_store_path = vector_store_path
        self.vector_store = self._init_vector_store()

    def _init_vector_store(self):
        """初始化向量存储"""
        # 这里可以加载预置的金融知识库
        try:
            return Chroma(
                persist_directory=self.vector_store_path,
                embedding_function=self.embeddings
            )
        except:
            # 创建新的向量存储
            return Chroma.from_texts(
                texts=["金融知识库初始化..."],
                embedding=self.embeddings,
                persist_directory=self.vector_store_path
            )

    def retrieve(self, query: str, k: int = 3) -> str:
        """检索相关知识"""
        try:
            docs = self.vector_store.similarity_search(query, k=k)
            return "\n".join([doc.page_content for doc in docs])
        except Exception as e:
            print(f"检索失败: {e}")
            return ""