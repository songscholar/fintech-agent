from langchain.agents.middleware import before_model
from langchain_openai import ChatOpenAI

@before_model
class DynamicModelManager:
    """动态模型管理器"""

    def __init__(self):
        self.models = {
            "gpt-3.5-turbo": ChatOpenAI(model="gpt-3.5-turbo", temperature=0.7),
            "gpt-4": ChatOpenAI(model="gpt-4", temperature=0.7),
            "gpt-3.5-turbo-strict": ChatOpenAI(model="gpt-3.5-turbo", temperature=0.3),
        }
        self.default_model = "gpt-3.5-turbo"

    def get_model(self, model_name: str = None) -> ChatOpenAI:
        """获取模型实例"""
        if model_name and model_name in self.models:
            return self.models[model_name]
        return self.models[self.default_model]

    def select_model_based_on_type(self, question_type: str) -> ChatOpenAI:
        """根据问题类型选择模型"""
        if question_type == "business":
            # 业务问题使用更严格的模型
            return self.get_model("gpt-3.5-turbo-strict")
        return self.get_model()