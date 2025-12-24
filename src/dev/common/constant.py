# config.py - 全局配置专用文件
# 1. 基础常量（全大写，区分普通变量）
PROJECT_NAME = "fintech-agent"
VERSION = "1.0.0"

# 2. 金融合规相关配置
FORBIDDEN_KEYWORDS = ["内幕交易", "保本保收益", "代客理财", "洗钱", "非法集资"]
MAX_RETRY_COUNT = 3
COMPLIANCE_MODEL = "gpt-3.5-turbo"

# 3. 模型配置（结构化，易维护）
OPENAI_CONFIG = {
    "api_key_env": "OPENAI_API_KEY",
    "base_url_env": "OPENAI_BASE_URL",
    "temperature": 0.1
}
ZHIPUAI_CONFIG = {
    "api_key_env": "ZHIPUAI_API_KEY",
    "base_url_env": "ZHIPUAI_BASE_URL",
    "model": "ernie-3.5-turbo"
}

# 4. 路径配置（动态计算，适配不同环境）
import os
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # 项目根目录
ENV_PATH = PROJECT_ROOT / ".env"
CHROMA_DB_PATH = PROJECT_ROOT / "data" / "chroma_db"