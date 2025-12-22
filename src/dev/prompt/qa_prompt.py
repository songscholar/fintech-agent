from langchain.agents.middleware import dynamic_prompt

# ============== 2. 动态提示词管理 ==============
@dynamic_prompt
class QAPromptManager:
    """动态提示词管理器"""

    def __init__(self):
        self.prompt_templates = {
            "business": """
            你是一个专业的金融顾问。请基于以下上下文信息，专业地回答用户的业务问题。

            上下文信息：
            {context}

            用户问题：
            {question}

            请确保你的回答：
            1. 准确、专业、可靠
            2. 基于提供的上下文信息
            3. 如有必要，可以建议用户咨询具体的金融顾问
            4. 符合金融行业规范和法律法规

            回答：
            """,

            "general": """
            你是一个有帮助的AI助手。请基于以下上下文信息，友好地回答用户的普通问题。

            上下文信息：
            {context}

            用户问题：
            {question}

            请确保你的回答：
            1. 友好、有帮助
            2. 基于提供的上下文信息
            3. 如果不知道，请诚实地说明
            4. 保持积极和建设性

            回答：
            """,

            "type_classification": """
            请判断以下问题是关于金融业务的还是普通问题：

            问题：{question}

            如果是关于以下金融业务的问题，请回答"business"：
            - 投资理财
            - 贷款业务
            - 信用卡
            - 保险
            - 股票基金
            - 银行业务
            - 风险管理
            - 金融法规
            - 金融产品
            - 财务报表

            如果是其他类型的普通问题，请回答"general"。

            只返回"business"或"general"：
            """,

            "validation": """
            请验证以下回答是否满足要求：

            原始问题：{question}
            回答：{answer}

            要求：
            1. 回答是否准确回答了问题
            2. 是否基于提供的上下文
            3. 是否专业、可靠（对于业务问题）
            4. 是否友好、有帮助（对于普通问题）
            5. 是否包含不适当或不确定的内容

            请只返回"通过"或"不通过"：
            """
        }

    def get_prompt(self, prompt_type: str, **kwargs) -> str:
        """获取动态提示词"""
        template = self.prompt_templates.get(prompt_type, "{question}")
        return template.format(**kwargs)

    def update_prompt_template(self, prompt_type: str, template: str):
        """更新提示词模板"""
        self.prompt_templates[prompt_type] = template
