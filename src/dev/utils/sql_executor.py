import re
from typing import Dict, Any, List
from datetime import datetime
import copy

from sqlalchemy import text

from src.dev.database.db_connection_manager import DatabaseConnectionManager
from src.dev.state.graph_state import DatabaseGraphState


class SQLExecutor:
    """SQL执行器 - 支持验证、执行和人工审核"""

    def __init__(self, db_connection_manager: DatabaseConnectionManager):
        self.db_manager = db_connection_manager
        self.human_approval_queue = []

    def validate_sql(self, sql: str, sql_type: str, engine) -> Dict[str, Any]:
        """
        验证SQL语句

        Returns:
            验证结果字典
        """
        validation_result = {
            "is_valid": False,
            "errors": [],
            "warnings": [],
            "estimated_cost": 0,
            "requires_human_approval": False
        }

        try:
            # 1. 基本语法检查
            sql = sql.strip()
            if not sql:
                validation_result["errors"].append("SQL语句为空")
                return validation_result

            # 2. 检测SQL类型
            sql_upper = sql.upper()
            if "SELECT" in sql_upper:
                detected_type = "SELECT"
            elif "INSERT" in sql_upper:
                detected_type = "INSERT"
            elif "UPDATE" in sql_upper:
                detected_type = "UPDATE"
            elif "DELETE" in sql_upper:
                detected_type = "DELETE"
            else:
                detected_type = "OTHER"

            # 3. 检查是否匹配声明的类型
            if sql_type and sql_type != detected_type:
                validation_result["warnings"].append(
                    f"SQL类型不匹配: 声明为{sql_type}，检测为{detected_type}"
                )

            # 4. 安全检查
            security_issues = self._check_sql_security(sql)
            if security_issues:
                validation_result["errors"].extend(security_issues)

            # 5. 语法检查（使用数据库的EXPLAIN或PREPARE）
            try:
                with engine.connect() as conn:
                    if "SELECT" in sql_upper:
                        # 尝试执行EXPLAIN来验证
                        explain_sql = f"EXPLAIN {sql}"
                        conn.execute(text(explain_sql))
                    else:
                        # 对于DML，尝试PREPARE
                        conn.execute(text(f"PREPARE test_stmt AS {sql}"))
                        conn.execute(text("DEALLOCATE test_stmt"))
            except Exception as e:
                validation_result["errors"].append(f"SQL语法错误: {str(e)}")

            # 6. 判断是否需要人工审核
            if detected_type in ["INSERT", "UPDATE", "DELETE"]:
                validation_result["requires_human_approval"] = True
                validation_result["warnings"].append("DML操作需要人工审核")

            # 7. 估算执行成本
            validation_result["estimated_cost"] = self._estimate_execution_cost(sql, engine)

            # 8. 如果没有错误，标记为有效
            if not validation_result["errors"]:
                validation_result["is_valid"] = True

            return validation_result

        except Exception as e:
            validation_result["errors"].append(f"验证过程异常: {str(e)}")
            return validation_result

    def _check_sql_security(self, sql: str) -> List[str]:
        """检查SQL安全"""
        security_issues = []

        # 黑名单关键词
        dangerous_patterns = [
            r"DROP\s+(TABLE|DATABASE|INDEX)",
            r"TRUNCATE\s+TABLE",
            r"ALTER\s+TABLE.*DROP",
            r"GRANT\s+.*TO",
            r"REVOKE\s+.*FROM",
            r";\s*--",  # SQL注入特征
            r"UNION\s+SELECT.*FROM",  # 简单的UNION注入检测
        ]

        for pattern in dangerous_patterns:
            if re.search(pattern, sql, re.IGNORECASE):
                security_issues.append(f"检测到危险操作: {pattern}")

        return security_issues

    def _estimate_execution_cost(self, sql: str, engine) -> int:
        """估算SQL执行成本（简化版）"""
        try:
            with engine.connect() as conn:
                # 尝试获取执行计划
                explain_result = conn.execute(text(f"EXPLAIN {sql}"))
                rows = list(explain_result)

                # 简单估算：行数越多成本越高
                cost = len(rows) * 10

                # 如果有全表扫描，增加成本
                sql_upper = sql.upper()
                if "WHERE" not in sql_upper:
                    cost *= 2

                return min(cost, 1000)  # 限制最大成本
        except:
            return 50  # 默认成本

    def execute_sql(self, sql: str, engine, limit: int = 1000) -> Dict[str, Any]:
        """
        执行SQL查询

        Returns:
            执行结果字典
        """
        result = {
            "success": False,
            "data": None,
            "row_count": 0,
            "execution_time": 0,
            "columns": [],
            "error": None
        }

        try:
            start_time = datetime.now()

            with engine.connect() as conn:
                # 对于SELECT查询，添加LIMIT
                if "SELECT" in sql.upper() and "LIMIT" not in sql.upper():
                    sql = f"{sql} LIMIT {limit}"

                # 执行SQL
                db_result = conn.execute(text(sql))

                # 获取列名
                result["columns"] = list(db_result.keys())

                # 获取数据
                rows = db_result.fetchall()
                result["data"] = [dict(row) for row in rows]
                result["row_count"] = len(rows)

                # 计算执行时间
                execution_time = (datetime.now() - start_time).total_seconds()
                result["execution_time"] = execution_time
                result["success"] = True

                print(f"✅ SQL执行成功: {result['row_count']}行, {execution_time:.2f}秒")

        except Exception as e:
            result["error"] = str(e)
            result["success"] = False
            print(f"❌ SQL执行失败: {str(e)}")

        return result

    def add_to_approval_queue(self, sql: str, reason: str, state: DatabaseGraphState):
        """添加到人工审核队列"""
        approval_item = {
            "sql": sql,
            "reason": reason,
            "state": copy.deepcopy(state.to_dict()),
            "timestamp": datetime.now().isoformat(),
            "session_id": state.session_id
        }
        self.human_approval_queue.append(approval_item)
        return len(self.human_approval_queue) - 1  # 返回队列索引
