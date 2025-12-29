import os
import logging
import uuid
from datetime import datetime
from pathlib import Path
import requests
from typing import List, Optional, Iterable, Tuple
from langchain_community.document_loaders import PyPDFLoader

import chardet
import yaml
from langchain_community.document_loaders import WebBaseLoader, PyMuPDFLoader, TextLoader, UnstructuredMarkdownLoader, \
    Docx2txtLoader, UnstructuredImageLoader
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from tqdm import tqdm  # 进度条，提升体验

# 导入你已有的加载函数和依赖
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings  # 若用开源模型，替换为HuggingFaceEmbeddings

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("document_vector_store")

from config import config


# 加载配置文件
def load_config(config_path: str = "config.yaml") -> dict:
    """加载config.yaml配置"""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        logger.info(f"✅ 成功加载配置文件：{config_path}")
        return config
    except FileNotFoundError:
        logger.error(f"❌ 配置文件不存在：{config_path}")
        raise
    except Exception as e:
        logger.error(f"❌ 加载配置失败：{str(e)}")
        raise


# 金融文本优化的切分器
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=config["CHUNK_SIZE"],  # 字典键取值
    chunk_overlap=config["CHUNK_OVERLAP"],
    separators=config["SEPARATORS"],
    length_function=len
)

# 金融领域嵌入模型
embeddings = HuggingFaceEmbeddings(
    model_name=config["EMBEDDING_MODEL"],
    model_kwargs={"device": "cuda" if config["EMBEDDING_USE_GPU"] else "cpu"},  # 区分嵌入模型的GPU配置
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
        loader = PyPDFLoader(file_path)
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
            file_path
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
            # 合并元数据时，保留原文档的页码（如PDF的page字段）
            merged_metadata = {**doc.metadata, **base_metadata, "chunk_raw_id": i}
            # 确保页码字段存在（针对PDF等格式）
            if "page" not in merged_metadata:
                merged_metadata["page"] = i + 1  # 默认为文档中的第i+1页
            enhanced_docs.append(Document(page_content=doc.page_content, metadata=merged_metadata))

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


class DocumentVectorStore:
    """文档向量化存储管理器：分离「加载」和「存储」逻辑"""

    def __init__(self, config: dict, vector_store_path: str = "./chroma_db"):
        self.config = config
        self.vector_store_path = vector_store_path
        self.supported_extensions = set(config["LOADER"]["SUPPORTED_EXTENSIONS"])
        self.embeddings = self._init_embeddings()
        self.vector_store = self._init_vector_store()

    def _init_embeddings(self):
        """初始化嵌入模型（兼容OpenAI/开源模型）"""
        # 方式1：使用OpenAI Embeddings（需配置OPENAI_API_KEY）
        try:
            return OpenAIEmbeddings()
        except Exception:
            # 方式2：使用开源中文嵌入模型（从配置读取）
            from langchain_community.embeddings import HuggingFaceEmbeddings
            return HuggingFaceEmbeddings(
                model_name=self.config["EMBEDDING_MODEL"],
                model_kwargs={"device": "cuda" if self.config["OCR_USE_GPU"] else "cpu"},
                encode_kwargs={"normalize_embeddings": True}
            )

    def _init_vector_store(self):
        """初始化Chroma向量存储（避免类名冲突+正确实例化）"""
        try:
            # 变量名用vector_store，避免和Chroma类名冲突
            vector_store = Chroma(
                persist_directory=self.vector_store_path,
                embedding_function=self.embeddings
            )
            logger.info(f"✅ 成功加载向量库：{self.vector_store_path}")
            return vector_store
        except Exception as e:
            logger.warning(f"⚠️  加载向量库失败，创建新库：{str(e)}")
            # from_texts是类方法，返回实例，无调用冲突
            return Chroma.from_texts(
                texts=["向量库初始化占位符"],
                embedding=self.embeddings,
                persist_directory=self.vector_store_path
            )

    def scan_directory(self, dir_path: str, recursive: bool = True) -> List[str]:
        """
        扫描指定目录，返回所有支持的文件路径
        :param dir_path: 目标目录
        :param recursive: 是否递归遍历子目录
        :return: 符合条件的文件路径列表
        """
        if not os.path.exists(dir_path):
            logger.error(f"❌ 目录不存在：{dir_path}")
            return []

        file_paths = []
        walk_iter = os.walk(dir_path) if recursive else [(dir_path, [], os.listdir(dir_path))]

        for root, _, files in walk_iter:
            for file in files:
                file_path = Path(root) / file
                # 过滤支持的文件后缀
                if file_path.suffix.lower() in self.supported_extensions:
                    # 过滤超大文件（从配置读取阈值）
                    max_size = self.config["LOADER"]["MAX_FILE_SIZE_MB"] * 1024 * 1024
                    if file_path.stat().st_size <= max_size:
                        file_paths.append(str(file_path))
                    else:
                        logger.warning(
                            f"⚠️ 文件过大跳过：{file_path}（大小：{file_path.stat().st_size / 1024 / 1024:.2f}MB）")

        logger.info(f"✅ 扫描完成，找到 {len(file_paths)} 个支持的文件")
        return file_paths

    def batch_load_documents(self, file_paths: List[str]) -> List[Document]:
        """
        批量加载文件（调用你的load_document），单个文件失败不影响整体
        :param file_paths: 扫描得到的文件路径列表
        :return: 所有加载成功的Document列表
        """
        all_docs = []
        failed_files = []

        for file_path in tqdm(file_paths, desc="📄 批量加载文件"):
            try:
                # 调用你已有的load_document方法
                docs = load_document(
                    file_path=file_path,
                    source_name=file_path,
                    encoding=""  # 自动检测编码
                )
                if docs:
                    all_docs.extend(docs)
                    logger.info(f"✅ 加载成功：{file_path}（生成 {len(docs)} 个文本块）")
                else:
                    logger.warning(f"⚠️ 无内容：{file_path}")
            except Exception as e:
                failed_files.append((file_path, str(e)))
                logger.error(f"❌ 加载失败：{file_path} - {str(e)}")

        # 输出加载统计
        logger.info(f"\n📊 批量加载统计：")
        logger.info(f"   总文件数：{len(file_paths)}")
        logger.info(f"   成功加载：{len(file_paths) - len(failed_files)}")
        logger.info(f"   失败数：{len(failed_files)}")
        logger.info(f"   生成文本块总数：{len(all_docs)}")

        if failed_files:
            logger.warning(f"❌ 失败文件列表：{[f[0] for f in failed_files]}")

        return all_docs

    def store_embeddings(self, docs: Iterable[Document], batch_size: int = 100):
        """
        向量化存储（支持单独执行）
        :param docs: 加载完成的Document列表（可来自任意来源，不一定是本地文件）
        :param batch_size: 批量存储大小（避免内存溢出）
        """
        if not docs:
            logger.warning("⚠️ 无文档可存储")
            return

        # 转换为列表（兼容迭代器）
        docs_list = list(docs)
        logger.info(f"📥 开始向量化存储，共 {len(docs_list)} 个文本块，批量大小：{batch_size}")

        # 批量存储
        for i in tqdm(range(0, len(docs_list), batch_size), desc="🔍 向量化存储"):
            batch_docs = docs_list[i:i + batch_size]
            ids = [f"doc_{uuid.uuid4()}" for _ in batch_docs]

            # 直接传 Document 列表，无需手动拆分
            self.vector_store.add_documents(
                documents=batch_docs,
                ids=ids
            )

        logger.info(f"✅ 向量化存储完成，共存储 {len(docs_list)} 个文本块")

    def run_full_pipeline(self, dir_path: str, recursive: bool = True):
        """
        一键执行：扫描目录 → 批量加载 → 向量化存储（整合流程）
        """
        logger.info("\n🚀 开始执行「扫描→加载→存储」全流程")
        # 1. 扫描目录
        file_paths = self.scan_directory(dir_path, recursive)
        if not file_paths:
            logger.error("❌ 无支持的文件，流程终止")
            return

        # 2. 批量加载
        docs = self.batch_load_documents(file_paths)
        if not docs:
            logger.error("❌ 无加载成功的文档，流程终止")
            return

        # 3. 向量化存储
        self.store_embeddings(docs)
        logger.info("\n🎉 全流程执行完成！")


# ------------------- 单独执行示例 -------------------
if __name__ == "__main__":
    # 1. 加载配置

    # 2. 初始化存储管理器
    vector_store = DocumentVectorStore(config, vector_store_path="../../../vector_data/chroma")

    # 方式1：执行全流程（扫描+加载+存储）
    vector_store.run_full_pipeline(
        dir_path="../../../fintech_file",  # 你的文档目录
        recursive=True  # 递归遍历子目录
    )

    # 方式2：单独执行向量化存储（比如加载好的docs列表）
    # docs = [Document(page_content="测试文本", metadata={"source": "test.txt"})]
    # vector_store.store_embeddings(docs)

    # 方式3：分步执行
    # file_paths = vector_store.scan_directory("./docs")
    # docs = vector_store.batch_load_documents(file_paths)
    # vector_store.store_embeddings(docs)
