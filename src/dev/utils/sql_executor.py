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
                    sql = f"{sql[:-1]} LIMIT {limit}"

                # 执行SQL
                db_result = conn.execute(text(sql))

                # 获取列名
                result["columns"] = list(db_result.keys())

                # 2. 获取数据（关键修改：手动构建字典，避免dict(row)转换错误）
                rows = db_result.fetchall()
                result["data"] = []
                for row in rows:
                    # 用“列名+对应的值”配对，构建字典（兼容所有SQLAlchemy版本）
                    row_dict = {col: row[i] for i, col in enumerate(result["columns"])}
                    result["data"].append(row_dict)
                    result["row_count"] += 1

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
