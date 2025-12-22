import hashlib
from datetime import datetime

from langchain_community.document_loaders import WebBaseLoader


# ============== 13. 辅助函数 ==============
def generate_session_id(user_input: str) -> str:
    """生成会话ID"""
    hash_obj = hashlib.md5(f"{user_input}_{datetime.now().timestamp()}".encode())
    return hash_obj.hexdigest()[:8]

def fetch_url_content(url: str) -> str:
    """获取URL内容"""
    try:
        loader = WebBaseLoader(url)
        documents = loader.load()
        content = "\n".join([doc.page_content[:1000] for doc in documents[:3]])  # 限制长度
        return f"来自 {url} 的内容：\n{content}"
    except Exception as e:
        return f"无法获取 {url} 的内容：{str(e)}"


def extract_file_content(file_reference: str) -> str:
    """提取文件内容（简化版）"""
    # 实际实现中需要处理文件上传
    return "从文件中提取的内容示例..."