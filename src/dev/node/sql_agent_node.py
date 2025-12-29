import os
import json
import re
from typing import Dict, List, Any
from datetime import datetime

from src.dev.database.db_connection_manager import DatabaseConnectionManager
from src.dev.moddleware.qa_moddleware import DynamicModelManager
from src.dev.prompt.qa_prompt import QAPromptManager
from src.dev.state.graph_state import DatabaseGraphState
from src.dev.utils.sql_executor import SQLExecutor

def parse_user_intent(state: DatabaseGraphState) -> DatabaseGraphState:
    """节点1: 解析用户意图"""
    print("🔍 解析用户意图...")

    user_input = state.user_input.lower()
    intent = {
        "action": "query",  # query, modify, describe, explain
        "target": "data",  # data, schema, both
        "complexity": "simple",  # simple, moderate, complex
        "tables": []
    }

    # 检测操作类型
    if any(word in user_input for word in ["查询", "查找", "获取", "select", "find"]):
        intent["action"] = "query"
    elif any(word in user_input for word in ["添加", "插入", "insert", "add"]):
        intent["action"] = "modify"
        intent["requires_human_approval"] = True
    elif any(word in user_input for word in ["更新", "修改", "update", "modify"]):
        intent["action"] = "modify"
        intent["requires_human_approval"] = True
    elif any(word in user_input for word in ["删除", "delete", "remove"]):
        intent["action"] = "modify"
        intent["requires_human_approval"] = True
    elif any(word in user_input for word in ["表结构", "schema", "结构", "describe"]):
        intent["action"] = "describe"
        intent["target"] = "schema"
    elif any(word in user_input for word in ["解释", "分析", "explain", "analyze"]):
        intent["action"] = "explain"

    # 检测目标表
    # 这里简化处理，实际应该使用NER或模型识别
    table_keywords = ["表", "table", "数据表"]
    for keyword in table_keywords:
        if keyword in user_input:
            # 提取表名模式
            words = user_input.split()
            for i, word in enumerate(words):
                if keyword in word and i < len(words) - 1:
                    potential_table = words[i + 1]
                    if len(potential_table) > 1:  # 简单过滤
                        intent["tables"].append(potential_table)

    # 检测复杂度
    if any(word in user_input for word in ["复杂", "关联", "join", "统计", "汇总"]):
        intent["complexity"] = "complex"
    elif any(word in user_input for word in ["简单", "基本", "单表"]):
        intent["complexity"] = "simple"
    else:
        intent["complexity"] = "moderate"

    state.parsed_intent = intent
    print(f"✅ 意图解析结果: {intent}")
    return state


def analyze_database_schema(state: DatabaseGraphState) -> DatabaseGraphState:
    """节点2: 分析数据库结构"""
    print("🏗️  分析数据库结构...")

    if not state.db_engine:
        print("⚠️  数据库未连接，跳过结构分析")
        return state

    try:
        # 获取数据库管理器
        db_manager = DatabaseConnectionManager()

        # 根据意图选择表
        if state.parsed_intent and state.parsed_intent.get("tables"):
            tables = state.parsed_intent["tables"]
        else:
            tables = None

        # 获取表结构元数据
        metadata = db_manager.get_table_metadata(state.db_engine, tables)

        # 如果用户询问表结构，直接生成回答
        if state.parsed_intent and state.parsed_intent.get("action") == "describe":
            schema_summary = format_schema_summary(metadata)
            state.final_answer = schema_summary

        state.db_metadata = metadata
        print(f"✅ 数据库结构分析完成: {len(metadata.get('tables', {}))}个表")

    except Exception as e:
        print(f"❌ 数据库结构分析失败: {str(e)}")
        state.db_metadata = {"error": str(e)}

    return state


def generate_sql_query(state: DatabaseGraphState) -> DatabaseGraphState:
    """节点3: 生成SQL查询"""
    print("🧠 生成SQL查询...")

    # 如果已经是表结构查询，跳过SQL生成
    if state.parsed_intent and state.parsed_intent.get("action") == "describe":
        return state

    try:
        prompt_manager = QAPromptManager()
        model_manager = DynamicModelManager()

        # 准备上下文
        schema_info = format_schema_for_prompt(state.db_metadata)
        user_intent = state.parsed_intent

        prompt = prompt_manager.get_prompt(
            "sql_generation",
            question=state.user_input,
            schema=schema_info,
            intent=json.dumps(user_intent, ensure_ascii=False)
        )

        # 选择模型 - 使用更强的模型生成SQL
        model = model_manager.get_model("gpt-4o", {"temperature": 0.1})

        # 生成SQL
        response = model.invoke(prompt)
        generated_sql = response.content.strip()

        # 清理SQL
        generated_sql = clean_generated_sql(generated_sql)

        # 检测SQL类型
        sql_type = detect_sql_type(generated_sql)

        state.generated_sql = generated_sql
        state.sql_type = sql_type

        print(f"✅ SQL生成完成: {sql_type} - {generated_sql[:100]}...")

    except Exception as e:
        print(f"❌ SQL生成失败: {str(e)}")
        state.sql_error = f"SQL生成失败: {str(e)}"

    return state


def validate_sql_statement(state: DatabaseGraphState) -> DatabaseGraphState:
    """节点4: 验证SQL语句"""
    print("✅ 验证SQL语句...")

    if not state.generated_sql:
        print("⚠️  无SQL语句需要验证")
        return state

    try:
        sql_executor = SQLExecutor(DatabaseConnectionManager())
        validation_result = sql_executor.validate_sql(
            state.generated_sql,
            state.sql_type,
            state.db_engine
        )

        state.sql_validation_result = validation_result
        state.requires_human_approval = validation_result.get("requires_human_approval", False)

        if validation_result["is_valid"]:
            print("✅ SQL验证通过")
        else:
            print(f"❌ SQL验证失败: {validation_result.get('errors', [])}")

    except Exception as e:
        print(f"❌ SQL验证异常: {str(e)}")
        state.sql_validation_result = {
            "is_valid": False,
            "errors": [f"验证异常: {str(e)}"]
        }

    return state


def check_human_approval(state: DatabaseGraphState) -> DatabaseGraphState:
    """节点5: 检查是否需要人工审核"""
    print("👥 检查人工审核需求...")

    if state.requires_human_approval and not state.human_approved:
        print("⏳ DML操作需要人工审核，添加到审核队列")

        # 创建SQL执行器
        sql_executor = SQLExecutor(DatabaseConnectionManager())

        # 添加到审核队列
        queue_index = sql_executor.add_to_approval_queue(
            sql=state.generated_sql,
            reason="DML操作需要人工审核",
            state=state
        )

        # 生成等待消息
        state.final_answer = (
            f"您的SQL操作需要人工审核，已加入审核队列（编号: {queue_index}）\n\n"
            f"**待审核SQL**:\n```sql\n{state.generated_sql}\n```\n\n"
            f"**审核原因**: {state.sql_validation_result.get('warnings', ['DML操作'])[0]}\n\n"
            f"请等待管理员审核后继续执行。"
        )

    return state


def execute_sql_query(state: DatabaseGraphState) -> DatabaseGraphState:
    """节点6: 执行SQL查询"""
    print("🚀 执行SQL查询...")

    if not state.generated_sql:
        print("⚠️  无SQL语句需要执行")
        return state

    # 检查是否需要人工审核
    if state.requires_human_approval and not state.human_approved:
        print("⏳ 等待人工审核，跳过执行")
        return state

    try:
        sql_executor = SQLExecutor(DatabaseConnectionManager())
        execution_result = sql_executor.execute_sql(
            state.generated_sql,
            state.db_engine,
            limit=1000  # 生产环境限制
        )

        state.sql_execution_result = execution_result

        if execution_result["success"]:
            print(f"✅ SQL执行成功: {execution_result['row_count']}行数据")

            # 格式化结果
            formatted_result = format_execution_result(execution_result)
            state.final_answer = formatted_result

        else:
            print(f"❌ SQL执行失败: {execution_result.get('error')}")
            state.sql_error = execution_result.get('error', "未知错误")

    except Exception as e:
        print(f"❌ SQL执行异常: {str(e)}")
        state.sql_error = str(e)

    return state


def self_correction_loop(state: DatabaseGraphState) -> DatabaseGraphState:
    """节点7: 自我修正循环"""
    print("🔄 进入自我修正循环...")

    # 检查重试次数
    if state.retry_count >= state.max_retries:
        print(f"⛔ 达到最大重试次数 ({state.max_retries})，终止循环")
        return state

    # 检查是否有错误需要修正
    if state.sql_error or (state.sql_validation_result and not state.sql_validation_result["is_valid"]):
        state.retry_count += 1

        print(f"🔄 第 {state.retry_count} 次重试修正...")

        # 分析错误原因
        error_messages = []
        if state.sql_error:
            error_messages.append(state.sql_error)
        if state.sql_validation_result and state.sql_validation_result.get("errors"):
            error_messages.extend(state.sql_validation_result["errors"])

        # 调用修正逻辑
        corrected_sql = correct_sql_with_errors(
            state.generated_sql,
            error_messages,
            state.db_metadata
        )

        if corrected_sql and corrected_sql != state.generated_sql:
            print(f"✅ SQL修正成功: {corrected_sql[:100]}...")
            state.generated_sql = corrected_sql
            state.sql_error = ""
        else:
            print("⚠️  SQL修正未产生新语句")

    return state


def finalize_response(state: DatabaseGraphState) -> DatabaseGraphState:
    """节点8: 最终化响应"""
    print("🎯 最终化响应...")

    # 如果没有最终答案，生成一个
    if not state.final_answer:
        if state.sql_error:
            state.final_answer = (
                f"抱歉，处理您的请求时出现错误:\n\n"
                f"**错误信息**: {state.sql_error}\n\n"
                f"请检查您的查询或联系管理员。"
            )
        elif state.generated_sql:
            state.final_answer = (
                f"SQL已生成但未执行:\n\n"
                f"```sql\n{state.generated_sql}\n```\n\n"
                f"类型: {state.sql_type}\n"
                f"状态: {'已验证' if state.sql_validation_result.get('is_valid') else '未验证'}"
            )
        else:
            state.final_answer = "未能处理您的请求，请提供更详细的信息。"

    # 添加执行统计
    if state.sql_execution_result and state.sql_execution_result["success"]:
        execution_stats = (
            f"\n\n---\n"
            f"**执行统计**:\n"
            f"- 返回行数: {state.sql_execution_result['row_count']}\n"
            f"- 执行时间: {state.sql_execution_result['execution_time']:.2f}秒\n"
            f"- 查询列数: {len(state.sql_execution_result.get('columns', []))}"
        )
        state.final_answer += execution_stats

    # 记录日志
    log_interaction(state)

    print("✅ 响应最终化完成")
    return state


# ============== 5. 辅助方法 ==============

def format_schema_for_prompt(self, metadata: Dict) -> str:
    """格式化表结构信息用于提示词"""
    if not metadata or "tables" not in metadata:
        return "无可用表结构信息"

    schema_text = "数据库表结构:\n\n"

    for table_name, table_info in metadata.get("tables", {}).items():
        schema_text += f"表名: {table_name}\n"

        # 添加列信息
        if "columns" in table_info:
            schema_text += "列:\n"
            for col in table_info["columns"]:
                nullable = "NULL" if col.get("nullable", True) else "NOT NULL"
                default = f" DEFAULT {col.get('default')}" if col.get("default") else ""
                comment = f" COMMENT '{col.get('comment', '')}'" if col.get("comment") else ""

                schema_text += f"  - {col['name']}: {col['type']} {nullable}{default}{comment}\n"

        # 添加主键信息
        if "primary_keys" in table_info and table_info["primary_keys"].get("constrained_columns"):
            pks = table_info["primary_keys"]["constrained_columns"]
            schema_text += f"主键: {', '.join(pks)}\n"

        # 添加外键信息
        if "foreign_keys" in table_info:
            for fk in table_info["foreign_keys"]:
                schema_text += f"外键: {fk.get('constrained_columns', [])} → {fk.get('referred_table', '')}.{fk.get('referred_columns', [])}\n"

        # 添加行数统计
        if "row_count" in table_info:
            schema_text += f"行数: {table_info['row_count']}\n"

        schema_text += "\n"

    return schema_text


def clean_generated_sql(self, sql: str) -> str:
    """清理生成的SQL"""
    # 移除SQL标记
    sql = sql.replace("```sql", "").replace("```", "").strip()

    # 移除多余的空格和换行
    sql = re.sub(r'\s+', ' ', sql)

    # 确保以分号结尾
    if not sql.endswith(';'):
        sql += ';'

    return sql


def format_schema_summary(metadata: Dict[str, Any]) -> str:
    """格式化表结构摘要"""
    if not metadata or "tables" not in metadata:
        return "无可用表结构信息"

    summary = "📋 数据库表结构摘要：\n\n"

    for table_name, table_info in metadata.get("tables", {}).items():
        summary += f"**表名**: {table_name}\n"

        # 列数
        column_count = len(table_info.get("columns", []))
        summary += f"  列数: {column_count}\n"

        # 行数
        row_count = table_info.get("row_count", 0)
        summary += f"  行数: {row_count}\n"

        # 主键
        pk_info = table_info.get("primary_keys", {})
        if pk_info and pk_info.get("constrained_columns"):
            pks = pk_info["constrained_columns"]
            summary += f"  主键: {', '.join(pks)}\n"

        # 列信息（只显示前5个）
        columns = table_info.get("columns", [])[:5]
        if columns:
            summary += "  主要列:\n"
            for col in columns:
                nullable = "NULL" if col.get("nullable", True) else "NOT NULL"
                summary += f"    - {col['name']} ({col['type']}) {nullable}\n"

        if column_count > 5:
            summary += f"    ... 还有 {column_count - 5} 个列\n"

        summary += "\n"

    # 统计信息
    table_count = len(metadata.get("tables", {}))
    total_columns = sum(len(t.get("columns", [])) for t in metadata.get("tables", {}).values())
    total_rows = sum(t.get("row_count", 0) for t in metadata.get("tables", {}).values())

    summary += f"📊 统计信息：\n"
    summary += f"  总表数: {table_count}\n"
    summary += f"  总列数: {total_columns}\n"
    summary += f"  总行数: {total_rows}\n"

    return summary

def detect_sql_type(self, sql: str) -> str:
    """检测SQL类型"""
    sql_upper = sql.upper()

    if "SELECT" in sql_upper:
        return "SELECT"
    elif "INSERT" in sql_upper:
        return "INSERT"
    elif "UPDATE" in sql_upper:
        return "UPDATE"
    elif "DELETE" in sql_upper:
        return "DELETE"
    elif "CREATE" in sql_upper or "ALTER" in sql_upper or "DROP" in sql_upper:
        return "DDL"
    else:
        return "OTHER"


def format_execution_result(self, result: Dict) -> str:
    """格式化执行结果"""
    if not result.get("success"):
        return f"执行失败: {result.get('error', '未知错误')}"

    row_count = result.get("row_count", 0)
    columns = result.get("columns", [])
    data = result.get("data", [])
    exec_time = result.get("execution_time", 0)

    response = f"✅ 查询成功！\n\n"
    response += f"**统计信息**:\n"
    response += f"- 返回行数: {row_count}\n"
    response += f"- 执行时间: {exec_time:.2f}秒\n"
    response += f"- 查询列数: {len(columns)}\n\n"

    if row_count > 0:
        response += f"**数据预览** (最多显示10行):\n\n"

        # 表头
        header = "| " + " | ".join(columns) + " |"
        separator = "|" + "|".join(["---" for _ in columns]) + "|"

        response += f"{header}\n{separator}\n"

        # 数据行
        for i, row in enumerate(data[:10]):
            row_values = [str(row.get(col, ""))[:50] for col in columns]  # 限制长度
            response += "| " + " | ".join(row_values) + " |\n"

        if row_count > 10:
            response += f"\n... 还有 {row_count - 10} 行数据未显示\n"
    else:
        response += "**查询结果为空**\n"

    return response


def correct_sql_with_errors(self, original_sql: str, errors: List[str], schema: Dict) -> str:
    """根据错误修正SQL"""
    try:
        prompt_manager = QAPromptManager()
        model_manager = DynamicModelManager()

        prompt = prompt_manager.get_prompt(
            "sql_correction",
            original_sql=original_sql,
            errors="\n".join(errors),
            schema=self._format_schema_for_prompt(schema)
        )

        model = model_manager.get_model("gpt-4o", {"temperature": 0.1})
        response = model.invoke(prompt)

        corrected_sql = response.content.strip()
        corrected_sql = self._clean_generated_sql(corrected_sql)

        return corrected_sql

    except Exception as e:
        print(f"❌ SQL修正失败: {str(e)}")
        return original_sql


def log_interaction(self, state: DatabaseGraphState):
    """记录交互日志"""
    log_entry = {
        "session_id": state.session_id,
        "timestamp": datetime.now().isoformat(),
        "user_input": state.user_input,
        "sql_generated": state.generated_sql,
        "sql_type": state.sql_type,
        "requires_human_approval": state.requires_human_approval,
        "human_approved": state.human_approved,
        "success": bool(state.sql_execution_result and state.sql_execution_result.get("success")),
        "row_count": state.sql_execution_result.get("row_count", 0) if state.sql_execution_result else 0,
        "error": state.sql_error
    }

    # 保存到日志文件
    log_dir = "logs/sql_agent"
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"{datetime.now().strftime('%Y-%m-%d')}.jsonl")

    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except:
        pass


# ============== 6. 条件判断函数 ==============

def should_require_human_approval(state: DatabaseGraphState) -> str:
    """判断是否需要人工审核"""
    if state.requires_human_approval and not state.human_approved:
        return "require_approval"
    return "continue_execution"


def should_retry_sql(state: DatabaseGraphState) -> str:
    """判断是否需要重试"""
    has_error = bool(state.sql_error) or (
            state.sql_validation_result and
            not state.sql_validation_result.get("is_valid", True)
    )

    if has_error and state.retry_count < state.max_retries:
        return "retry"
    return "continue"


def is_schema_query(state: DatabaseGraphState) -> str:
    """判断是否为表结构查询"""
    if state.parsed_intent and state.parsed_intent.get("action") == "describe":
        return "schema_query"
    return "data_query"