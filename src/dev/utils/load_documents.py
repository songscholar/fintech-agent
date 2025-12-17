import uuid
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
# 导入LangChain内置Loader
from langchain_community.document_loaders import (
    PyMuPDFLoader,       # PDF
    WebBaseLoader,       # HTML/URL
    TextLoader,          # TXT
    UnstructuredMarkdownLoader,  # MD
    Docx2txtLoader,      # DOCX
    UnstructuredImageLoader,     # 图片（需OCR依赖）
)

from config import config

# ====================== 1. 基础配置（复用原有） ======================
# 金融文本优化的切分器  todo
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=512,
    chunk_overlap=50,
    separators=["。", "！", "？", "；", "\n", " ", "，"],  # 中文金融文本适配
    length_function=len
)

# 金融领域嵌入模型 todo
embeddings = HuggingFaceEmbeddings(
    model_name=config.EMBEDDING_MODEL,
    model_kwargs={"device": "cuda" if config.OCR_USE_GPU else "cpu"},
    encode_kwargs={"normalize_embeddings": True}
)

# ====================== 2. 通用文件加载器（核心简化） ======================
def load_document_generic(
    file_path: str,
    source_name: Optional[str] = None,
    encoding: str = "utf-8"
) -> List[Document]:
    """
    基于LangChain内置Loader的通用文件加载方法
    自动识别格式：PDF/HTML/URL/TXT/MD/DOCX/图片（JPG/PNG等）
    :param file_path: 文件路径/URL（URL需以http/https开头）
    :param source_name: 自定义来源名称（用于标注引用）
    :param encoding: 文本编码（适配国内金融文档）
    :return: 带金融元数据的Document列表（已切分）
    """
    # 基础元数据（所有格式通用）
    base_metadata = {
        "source": source_name or file_path,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "doc_id": str(uuid.uuid4()),
        "file_size": str(Path(file_path).stat().st_size) + " bytes" if not file_path.startswith(("http", "https")) else "unknown"
    }

    # 步骤1：判断URL/本地文件，选择对应Loader
    try:
        if file_path.startswith(("http://", "https://")):
            # HTML/URL加载
            loader = WebBaseLoader(
                file_path,
                verify_ssl=False,  # 适配国内网站SSL场景
                encoding=encoding
            )
            base_metadata["file_type"] = "html"
        else:
            # 本地文件：按后缀识别格式
            suffix = Path(file_path).suffix.lower()
            if suffix == ".pdf":
                loader = PyMuPDFLoader(file_path)
                base_metadata["file_type"] = "pdf"
            elif suffix == ".txt":
                loader = TextLoader(file_path, encoding=encoding)
                base_metadata["file_type"] = "txt"
            elif suffix == ".md":
                loader = UnstructuredMarkdownLoader(file_path, encoding=encoding)
                base_metadata["file_type"] = "md"
            elif suffix == ".docx":
                loader = Docx2txtLoader(file_path)
                base_metadata["file_type"] = "docx"
            elif suffix in [".jpg", ".jpeg", ".png", ".bmp", ".tiff"]:
                # 图片加载（需安装：pip install unstructured[local-inference] paddleocr）
                loader = UnstructuredImageLoader(
                    file_path,
                    strategy="ocr_only",  # 仅OCR提取文字（适配行情截图）
                    ocr_language="chi_sim"  # 中文OCR
                )
                base_metadata["file_type"] = "image"
                base_metadata["image_size"] = f"{Path(file_path).stat().st_size} bytes"  # 简化版尺寸
            else:
                raise ValueError(f"不支持的文件格式：{suffix}")

        # 步骤2：加载文档并补充元数据
        raw_docs = loader.load()
        if not raw_docs:
            return []

        # 步骤3：为每个原始文档补充金融元数据
        enhanced_docs = []
        for i, doc in enumerate(raw_docs):
            # 合并Loader默认元数据 + 自定义金融元数据
            doc.metadata = {**doc.metadata, **base_metadata, "chunk_raw_id": i}
            enhanced_docs.append(doc)

        # 步骤4：统一切分文本（保持金融文本完整性）
        split_docs = text_splitter.split_documents(enhanced_docs)

        # 步骤5：为切分后的chunk补充唯一ID
        for i, doc in enumerate(split_docs):
            doc.metadata["chunk_id"] = f"{doc.metadata['doc_id']}_{i}"

        return split_docs

    except Exception as e:
        # 兼容中文编码/文件不存在等常见异常
        raise ValueError(f"文件加载失败（{file_path}）：{str(e)}")

# ====================== 3. 来源格式化（复用原有，仅补充新格式） ======================
def format_sources(sources: List[Document]) -> str:
    """
    格式化引用来源（适配LangChain Loader的元数据）
    """
    if not sources:
        return "无引用来源"

    source_info = []
    for i, doc in enumerate(sources, 1):
        meta = doc.metadata
        source_type = meta.get("file_type", "unknown")
        source = meta.get("source", "unknown")
        timestamp = meta.get("timestamp", "unknown")

        # 按格式适配LangChain Loader的元数据
        format_map = {
            "pdf": f"{i}. PDF文档：{source}（页码：{meta.get('page', '未知')}）- 抓取时间：{timestamp}",
            "html": f"{i}. 网页资讯：{source}（标题：{meta.get('title', '未知')}）- 抓取时间：{timestamp}",
            "txt": f"{i}. 纯文本文档：{source}（编码：{meta.get('encoding', 'utf-8')}）- 抓取时间：{timestamp}",
            "md": f"{i}. Markdown文档：{source} - 抓取时间：{timestamp}",
            "docx": f"{i}. Word文档：{source} - 抓取时间：{timestamp}",
            "image": f"{i}. 图片文件：{source}（OCR提取）- 抓取时间：{timestamp}",
            "unknown": f"{i}. 未知来源：{source} - 抓取时间：{timestamp}"
        }
        source_info.append(format_map.get(source_type, format_map["unknown"]))

    return "\n".join(source_info)