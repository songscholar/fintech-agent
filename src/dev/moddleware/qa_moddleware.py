import os
from pathlib import Path
from typing import Optional, Dict, Any, Type
from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_deepseek import ChatDeepSeek
from langchain_qwq import ChatQwen

class DynamicModelManager:
    """
    LangChain 模型实例管理器（核心：只产出 Model 实例，不执行推理）
    作用：根据模型别名，从.env加载配置，返回对应的 LangChain ChatModel 实例
    """
    # 模型映射：别名 → (LangChain模型类, 配置前缀, 厂商原生模型名)
    MODEL_MAPPING: Dict[str, tuple[Type[BaseChatModel], str, str]] = {
        # OpenAI系列
        "gpt-3.5-turbo": (ChatOpenAI, "OPENAI", "gpt-3.5-turbo"),
        "gpt-4o": (ChatOpenAI, "OPENAI", "gpt-4o"),
        # Anthropic Claude
        "claude-3-haiku": (ChatAnthropic, "ANTHROPIC", "claude-3-haiku-20240307"),
        # 阿里通义千问（兼容OpenAI接口）
        "qwen-turbo": (ChatQwen, "ChatQwen", "qwen-turbo"),
        # deepseek
        "deepseek": (ChatDeepSeek, "DEEPSEEK", "deepseek-chat"),
        # 默认
        "default": (ChatOpenAI, "OPENAI", "gpt-3.5-turbo"),
    }

    def __init__(self, override_config: Optional[Dict[str, str]] = None):
        """
        初始化管理器（确保加载到项目根目录的.env文件）
        :param override_config: 全局配置覆盖（如{"OPENAI_BASE_URL": "代理地址"}）
        """
        # 🌟 核心修复：获取项目根目录的.env绝对路径（关键！）
        # 步骤1：找到项目根目录（根据实际目录结构调整，比如向上找包含.env的目录）
        # 方法：从当前文件所在目录，向上回溯到项目根目录（假设.env在项目根）
        current_file = Path(__file__).resolve()  # 当前脚本的绝对路径
        project_root = current_file.parents[3]  # 按需调整层级：0=当前文件目录，1=上一级，依此类推
        env_path = project_root / ".env"

        # 步骤2：加载.env并验证是否成功
        load_success = load_dotenv(dotenv_path=env_path, override=True)  # override=True：覆盖系统环境变量
        if not load_success:
            # 可选：警告但不报错（或抛异常，根据需求）
            print(f"警告：未找到.env文件（路径：{env_path}），请检查路径是否正确！")
        else:
            print(f"成功加载.env文件：{env_path}")

        # 步骤3：初始化覆盖配置
        self.override_config = override_config or {}

    def get_model(
        self,
        model_name: Optional[str] = None,
        model_kwargs: Optional[Dict[str, Any]] = None
    ) -> BaseChatModel:
        """
        核心方法：获取指定模型的 LangChain ChatModel 实例
        :param model_name: 模型别名（如gpt-3.5-turbo、ernie-3.5）
        :param model_kwargs: 模型初始化参数（如temperature、max_tokens）
        :return: LangChain BaseChatModel 实例
        """
        # 1. 校验模型是否支持
        if model_name not in self.MODEL_MAPPING:
            model_name = "gpt-3.5-turbo"
            # raise ValueError(
            #     f"不支持的模型：{model_name}，支持列表：{list(self.MODEL_MAPPING.keys())}"
            # )

        # 2. 获取模型配置
        chat_model_cls, config_prefix, real_model_name = self.MODEL_MAPPING[model_name]
        model_kwargs = model_kwargs or {"temperature": 0.1}

        # 3. 加载配置（.env + 覆盖配置）
        api_key = self._get_config(f"{config_prefix}_API_KEY")
        base_url = self._get_config(f"{config_prefix}_BASE_URL", required=False)

        # 4. 构建模型初始化参数
        init_kwargs = {
            "model_name": real_model_name,
            "api_key": api_key,
            **model_kwargs
        }
        if base_url:
            init_kwargs["base_url"] = base_url

        # 5. 返回 LangChain Model 实例（核心！只返回实例，不执行推理）
        return chat_model_cls(**init_kwargs)

    def _get_config(self, key: str, required: bool = True) -> Optional[str]:
        """获取配置（优先级：override_config > .env > None）"""
        # 优先使用覆盖配置
        if key in self.override_config:
            return self.override_config[key]
        # 其次从.env加载
        env_value = os.getenv(key)
        # 校验必填配置
        if required and not env_value:
            raise RuntimeError(f"请在.env中配置 {key} 环境变量！")
        return env_value

    @classmethod
    def register_model(
        cls,
        alias: str,
        chat_model_cls: Type[BaseChatModel],
        config_prefix: str,
        real_model_name: str
    ):
        """动态注册新模型（扩展用）"""
        cls.MODEL_MAPPING[alias] = (chat_model_cls, config_prefix, real_model_name)