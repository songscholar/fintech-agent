from langchain.agents.middleware import dynamic_prompt


# ============== 2. 动态提示词管理 ==============

class SQLPromptManager:
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
            """,

            "user_intent": """
            你是企业级数据库操作意图解析专家，负责精准识别用户对证券交易类数据库的操作意图，输出结构化结果。请严格按照以下要求执行：
            
            ### 核心任务
            分析用户输入，输出包含以下字段的 JSON 结构，字段不可缺失，值必须在指定可选范围内选择：
            
            ### 字段定义与约束
            1. **action**: 操作类型（必选，仅可选以下值）
               - "query": 数据查询（如查询、查找、获取数据，不修改数据库）
               - "modify": 数据修改（如插入、添加、更新、删除，会变更数据库数据）
               - "describe": 表结构查询（如查看表结构、字段说明、schema 信息）
               - "explain": 结果解释/分析（如解释查询结果、分析数据规律）
            
            2. **target**: 操作目标（必选，仅可选以下值）
               - "data": 操作数据库中的数据（查询/修改数据）
               - "schema": 操作数据库表结构（查看表定义、字段类型）
               - "both": 同时涉及数据和表结构（如"查询用户表的字段并统计数据行数"）
            
            3. **complexity**: 操作复杂度（必选，仅可选以下值）
               - "simple": 单表操作，无聚合/关联/复杂条件（如"查询用户表所有数据"、"查看交易表结构"）
               - "moderate": 单表聚合/简单条件查询（如"查询2023年的交易记录"、"统计用户表总人数"）
               - "complex": 多表关联、复杂统计/条件、子查询（如"统计每个用户的交易总额"、"查询跨表关联的订单数据"）
            
            4. **tables**: 涉及的数据库表名列表（必选，无明确表名则为空列表[]，需匹配实际可能的表名，如users/transactions）
               - 示例：用户说"交易记录"→表名是"transactions"；用户说"用户信息"→表名是"users"
            
            5. **requires_human_approval**: 是否需要人工审核（必选，布尔值）
               - 仅当 action 为 "modify" 时为 true（插入/更新/删除会变更数据，高危操作）
               - 其他 action（query/describe/explain）均为 false
            
            6. **remark**: 判断依据说明（可选，简要说明为何如此分类，方便调试）
            
            ### 严格规则
            1. 优先匹配证券交易数据库场景（核心表通常为：users(用户表)、transactions(交易表)、orders(订单表)、assets(资产表)）
            2. 模糊表述处理：用户未明确表名时，根据操作内容推断可能表名；无法推断则留空
            3. 高危操作校验：任何涉及"添加/插入/更新/修改/删除"的操作，action 必须为 "modify"，且 requires_human_approval 必须为 true
            4. 输出格式：仅返回 JSON 字符串，无多余文字，JSON 字段不可缺失，值必须符合可选范围
            
            ### 示例参考
            #### 示例1：用户输入 = "查看数据库中有哪些表"
            输出：
            {
              "action": "describe",
              "target": "schema",
              "complexity": "simple",
              "tables": [],
              "requires_human_approval": false,
              "remark": "用户查询数据库表清单，属于表结构描述操作，无具体表名，复杂度简单"
            }
            
            #### 示例2：用户输入 = "显示用户表的结构"
            输出：
            {
              "action": "describe",
              "target": "schema",
              "complexity": "simple",
              "tables": ["users"],
              "requires_human_approval": false,
              "remark": "用户明确查询用户表的结构，属于表结构描述操作，涉及表users"
            }
            
            #### 示例3：用户输入 = "查询用户表中的所有数据"
            输出：
            {
              "action": "query",
              "target": "data",
              "complexity": "simple",
              "tables": ["users"],
              "requires_human_approval": false,
              "remark": "单表全量查询，无复杂条件，属于简单数据查询"
            }
            
            #### 示例4：用户输入 = "统计每个用户的交易总额"
            输出：
            {
              "action": "query",
              "target": "data",
              "complexity": "complex",
              "tables": ["users", "transactions"],
              "requires_human_approval": false,
              "remark": "需关联用户表和交易表，涉及聚合统计，属于复杂查询"
            }
            
            #### 示例5：用户输入 = "向交易表添加一条新记录"
            输出：
            {
              "action": "modify",
              "target": "data",
              "complexity": "moderate",
              "tables": ["transactions"],
              "requires_human_approval": true,
              "remark": "添加记录属于数据修改操作，高危需审核，单表操作复杂度中等"
            }
            
            #### 示例6：用户输入 = "更新用户张三的手机号并查看修改结果"
            输出：
            {
              "action": "modify",
              "target": "both",
              "complexity": "moderate",
              "tables": ["users"],
              "requires_human_approval": true,
              "remark": "更新数据+查询结果，涉及数据修改和查询，需审核，单表操作复杂度中等"
            }
            
            #### 示例7：用户输入 = "查询2023年每个月的交易量"
            输出：
            {
              "action": "query",
              "target": "data",
              "complexity": "moderate",
              "tables": ["transactions"],
              "requires_human_approval": false,
              "remark": "单表按月份聚合统计，有时间条件，属于中等复杂度查询"
            }
            """
        }

    def get_prompt(self, prompt_type: str, **kwargs) -> str:
        """获取动态提示词"""
        template = self.prompt_templates.get(prompt_type, "{question}")
        return template.format(**kwargs)

    def update_prompt_template(self, prompt_type: str, template: str):
        """更新提示词模板"""
        self.prompt_templates[prompt_type] = template
