from langchain.agents.middleware import dynamic_prompt


# ============== 2. 动态提示词管理 ==============

class QAPromptManager:
    """动态提示词管理器"""

    def __init__(self):
        self.prompt_templates = {
            "sql_generation": """
            你是一个专业的SQL专家，需要根据用户的问题和数据库结构生成SQL查询。

            数据库表结构：
            {schema}

            用户问题：
            {question}

            用户意图分析：
            {intent}

            请遵循以下规则生成SQL：
            1. 优先使用SELECT查询，除非用户明确要求修改数据
            2. 对于数据修改操作（INSERT/UPDATE/DELETE），必须在注释中标记# DML_OPERATION
            3. 确保SQL语法正确，符合{db_type}数据库规范
            4. 使用合适的JOIN和WHERE条件
            5. 考虑性能，避免SELECT *
            6. 对于复杂查询，使用WITH子句或子查询
            7. 添加适当的注释说明查询目的

            请生成SQL语句：
            """,

            "sql_correction": """
            你需要修正一个SQL语句中的错误。

            原始SQL：
            {original_sql}

            错误信息：
            {errors}

            数据库表结构：
            {schema}

            请分析错误原因并提供修正后的SQL：
            1. 保持原始查询意图不变
            2. 修正语法错误
            3. 优化查询逻辑
            4. 确保符合数据库规范

            修正后的SQL：
            """,

            "sql_validation": """
            验证以下SQL语句的安全性和正确性：

            SQL语句：
            {sql}

            数据库类型：{db_type}

            请检查以下方面：
            1. 语法正确性
            2. 是否存在SQL注入风险
            3. 是否包含危险操作（DROP, TRUNCATE等）
            4. 权限是否足够
            5. 执行成本评估

            验证结果（JSON格式）：
            """,

            "sql_explanation": """
            请解释以下SQL语句：

            SQL语句：
            {sql}

            执行结果：
            {result}

            请从以下角度解释：
            1. 查询目的和逻辑
            2. 涉及的表和字段
            3. 执行计划分析
            4. 可能的性能问题
            5. 优化建议

            解释：
            """
        }

    def get_prompt(self, prompt_type: str, **kwargs) -> str:
        """获取动态提示词"""
        template = self.prompt_templates.get(prompt_type, "{question}")
        return template.format(**kwargs)

    def update_prompt_template(self, prompt_type: str, template: str):
        """更新提示词模板"""
        self.prompt_templates[prompt_type] = template
