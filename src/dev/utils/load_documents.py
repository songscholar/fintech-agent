import uuid
import chardet
from datetime import datetime
from typing import List, Optional, Tuple
from pathlib import Path
import requests

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.document_loaders import (
    PyMuPDFLoader,
    WebBaseLoader,
    TextLoader,
    UnstructuredMarkdownLoader,
    Docx2txtLoader,
    UnstructuredImageLoader,
)

from config import config

# 金融文本优化的切分器
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=config.CHUNK_SIZE,
    chunk_overlap=config.CHUNK_OVERLAP,
    separators=config.SEPARATORS,  # 从配置文件获取分隔符
    length_function=len
)

# 金融领域嵌入模型
embeddings = HuggingFaceEmbeddings(
    model_name=config.EMBEDDING_MODEL,
    model_kwargs={"device": "cuda" if config.EMBEDDING_USE_GPU else "cpu"},  # 区分嵌入模型的GPU配置
    encode_kwargs={"normalize_embeddings": True}
)


def _detect_encoding(file_path: str) -> str:
    """自动检测文件编码"""
    try:
        with open(file_path, 'rb') as f:
            raw_data = f.read(10000)  # 读取部分数据用于检测
        detected = chardet.detect(raw_data)
        return detected['encoding'] or 'utf-8'
    except Exception:
        return 'utf-8'  # 检测失败默认使用utf-8


def _get_loader_and_metadata(file_path: str, encoding: str) -> Tuple[object, dict]:
    """获取文件加载器和对应的元数据"""
    base_metadata = {}

    if file_path.startswith(("http://", "https://")):
        # 处理URL
        loader = WebBaseLoader(
            file_path,
            verify_ssl=False,
            encoding=encoding
        )
        base_metadata["file_type"] = "html"
        return loader, base_metadata

    # 处理本地文件
    file_path_obj = Path(file_path)
    suffix = file_path_obj.suffix.lower()

    # 补充文件基本元数据
    try:
        stat = file_path_obj.stat()
        base_metadata["file_size"] = f"{stat.st_size} bytes"
        base_metadata["file_modified"] = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        base_metadata["file_size"] = "unknown"
        base_metadata["file_modified"] = "unknown"

    # 根据后缀选择加载器
    if suffix == ".pdf":
        loader = PyMuPDFLoader(file_path)
        base_metadata["file_type"] = "pdf"
    elif suffix == ".txt":
        # 自动检测编码（如果未指定）
        used_encoding = encoding if encoding else _detect_encoding(file_path)
        loader = TextLoader(file_path, encoding=used_encoding)
        base_metadata["file_type"] = "txt"
        base_metadata["encoding"] = used_encoding
    elif suffix == ".md":
        loader = UnstructuredMarkdownLoader(file_path, encoding=encoding)
        base_metadata["file_type"] = "md"
    elif suffix == ".docx":
        loader = Docx2txtLoader(file_path)
        base_metadata["file_type"] = "docx"
    elif suffix in [".jpg", ".jpeg", ".png", ".bmp", ".tiff"]:
        loader = UnstructuredImageLoader(
            file_path,
            strategy="ocr_only",
            ocr_language="chi_sim"
        )
        base_metadata["file_type"] = "image"
    else:
        raise ValueError(f"不支持的文件格式：{suffix}")

    return loader, base_metadata


def load_document(
        file_path: str,
        source_name: Optional[str] = None,
        encoding: str = ""  # 空字符串表示自动检测
) -> List[Document]:
    """
    基于LangChain内置Loader的通用文件加载方法
    自动识别格式：PDF/HTML/URL/TXT/MD/DOCX/图片（JPG/PNG等）
    :param file_path: 文件路径/URL（URL需以http/https开头）
    :param source_name: 自定义来源名称（用于标注引用）
    :param encoding: 文本编码（空字符串则自动检测，主要用于TXT文件）
    :return: 带金融元数据的Document列表（已切分）
    """
    # 基础元数据（所有格式通用）
    base_metadata = {
        "source": source_name or file_path,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "doc_id": str(uuid.uuid4()),
    }

    try:
        # 获取加载器和类型元数据
        loader, type_metadata = _get_loader_and_metadata(file_path, encoding)
        # 合并元数据
        base_metadata.update(type_metadata)

        # 加载文档（针对需要资源管理的加载器使用上下文管理器）
        if isinstance(loader, PyMuPDFLoader):
            with loader:
                raw_docs = loader.load()
        else:
            raw_docs = loader.load()

        if not raw_docs:
            return []

        # 补充元数据并切分
        enhanced_docs = []
        for i, doc in enumerate(raw_docs):
            doc.metadata = {**doc.metadata, **base_metadata, "chunk_raw_id": i}
            enhanced_docs.append(doc)

        split_docs = text_splitter.split_documents(enhanced_docs)

        # 补充chunk唯一标识
        for i, doc in enumerate(split_docs):
            doc.metadata["chunk_id"] = f"{doc.metadata['doc_id']}_{i}"
            doc.metadata["chunk_total"] = len(split_docs)  # 总chunk数

        return split_docs

    except FileNotFoundError:
        raise ValueError(f"文件不存在：{file_path}")
    except PermissionError:
        raise ValueError(f"无权限访问文件：{file_path}")
    except requests.exceptions.RequestException as e:
        raise ValueError(f"URL请求失败（{file_path}）：{str(e)}")
    except Exception as e:
        raise ValueError(f"文件加载失败（{file_path}）：{str(e)}")


def format_document(sources: List[Document]) -> str:
    """格式化引用来源（适配LangChain Loader的元数据）"""
    if not sources:
        return "无引用来源"

    source_info = []
    for i, doc in enumerate(sources, 1):
        meta = doc.metadata
        source_type = meta.get("file_type", "unknown")
        source = meta.get("source", "unknown")
        timestamp = meta.get("timestamp", "unknown")

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