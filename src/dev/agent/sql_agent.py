"""
数据库智能体主模块 - 连接数据库执行SQL操作，支持人工审核和自动修正
企业级生产环境设计，支持证券交易数据库操作
"""

import os
from typing import Dict, Any, List, Optional
from langgraph.graph import StateGraph, END
from langgraph.constants import START
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from sqlalchemy import create_engine

from src.dev.database.db_connection_manager import DatabaseConnectionManager
from src.dev.node.sql_agent_node import parse_user_intent, generate_sql_query, validate_sql_statement, \
    execute_sql_query, check_human_approval, analyze_database_schema, self_correction_loop, finalize_response, \
    is_schema_query, should_require_human_approval, should_retry_sql
from src.dev.state.graph_state import DatabaseGraphState
from src.dev.utils.db_utils import DBEngineProvider
from src.dev.utils.scholar_tools import generate_session_id
from src.dev.utils.sql_executor import SQLExecutor

def build_database_agent():
    """
    构建数据库智能体流程图

    Args:
        db_connection_string: 数据库连接字符串
    """
    print("🏗️  构建数据库智能体流程图...")

    # 创建状态图
    workflow = StateGraph(DatabaseGraphState)

    # 添加节点
    workflow.add_node("parse_intent", parse_user_intent)
    workflow.add_node("analyze_schema", analyze_database_schema)
    workflow.add_node("generate_sql", generate_sql_query)
    workflow.add_node("validate_sql", validate_sql_statement)
    workflow.add_node("check_approval", check_human_approval)
    workflow.add_node("execute_sql", execute_sql_query)
    workflow.add_node("self_correction", self_correction_loop)
    workflow.add_node("finalize", finalize_response)

    # 设置入口
    workflow.add_edge(START, "parse_intent")

    # 解析意图后，判断是否是表结构查询
    workflow.add_conditional_edges(
        "parse_intent",
        is_schema_query,
        {
            "schema_query": "analyze_schema",  # 表结构查询直接分析
            "data_query": "analyze_schema"  # 数据查询也需要分析结构
        }
    )

    # 分析表结构后，生成SQL
    workflow.add_edge("analyze_schema", "generate_sql")

    # 生成SQL后，验证SQL
    workflow.add_edge("generate_sql", "validate_sql")

    # 验证SQL后，检查是否需要人工审核
    workflow.add_conditional_edges(
        "validate_sql",
        should_require_human_approval,
        {
            "require_approval": "check_approval",  # 需要人工审核
            "continue_execution": "execute_sql"  # 直接执行
        }
    )

    # 人工审核节点后，判断是否批准
    workflow.add_conditional_edges(
        "check_approval",
        lambda state: "approved" if state.human_approved else "waiting",
        {
            "approved": "execute_sql",  # 已批准，执行SQL
            "waiting": END  # 等待审核，结束流程
        }
    )

    # 执行SQL后，判断是否需要自我修正
    workflow.add_conditional_edges(
        "execute_sql",
        should_retry_sql,
        {
            "retry": "self_correction",  # 需要重试
            "continue": "finalize"  # 完成执行
        }
    )

    # 自我修正后，重新验证SQL
    workflow.add_edge("self_correction", "validate_sql")

    # 最终化响应后结束
    workflow.add_edge("finalize", END)

    # 编译图
    store = InMemoryStore()
    checkpointer = InMemorySaver()

    app = workflow.compile(
        store=store,
        checkpointer=checkpointer
    )

    print("✅ 数据库智能体流程图构建完成")
    return app


# ============== 8. 数据库智能体主类 ==============

class DatabaseAgent:
    """数据库智能体主类"""

    def __init__(self, db_connection_string: str = None):
        """
        初始化数据库智能体

        Args:
            db_connection_string: 数据库连接字符串
                格式: dialect+driver://username:password@host:port/database
                示例: mysql+pymysql://user:pass@localhost:3306/finance_db
        """
        self.db_connection_string = db_connection_string
        self.db_engine = None
        self.db_manager = DatabaseConnectionManager()

        # 初始化数据库连接
        if db_connection_string:
            self._initialize_database_connection()

        # 构建智能体
        self.app = build_database_agent()

        # 初始化SQL执行器
        self.sql_executor = SQLExecutor(self.db_manager)

    def _initialize_database_connection(self):
        """初始化数据库连接"""
        dbEngineProvider = DBEngineProvider()

        try:
            self.db_engine = dbEngineProvider.init_engine(self.db_connection_string)
            print(f"✅ 数据库连接初始化成功")
        except Exception as e:
            print(f"❌ 数据库连接初始化失败: {str(e)}")
            self.db_engine = None

    def ask(self, question: str, session_id: str = None, **kwargs) -> Dict[str, Any]:
        """
        提问入口

        Args:
            question: 用户问题
            session_id: 会话ID
            **kwargs: 额外参数

        Returns:
            回答结果字典
        """
        # 生成或使用会话ID
        if not session_id:
            session_id = generate_session_id(question)

        print(f"\n{'=' * 50}")
        print(f"会话: {session_id}")
        print(f"数据库问题: {question}")
        print(f"{'=' * 50}\n")

        # 准备初始状态
        initial_state = {
            "user_input": question,
            "session_id": session_id,
            "db_connection_string": self.db_connection_string,
            #todo 数据库类型以及数据源要修改成动态可配置的
            "db_type": "sqlite",
            "messages": [],
            "retry_count": 0,
            "max_retries": 3
        }

        # 更新额外参数
        for key, value in kwargs.items():
            if hasattr(initial_state, key):
                setattr(initial_state, key, value)

        # 执行流程图
        config = {"configurable": {"thread_id": session_id}}

        # try:
        #     result_state = self.app.invoke(initial_state, config)
        #
        #     # 返回结果
        #     return {
        #         "answer": result_state.final_answer,
        #         "session_id": session_id,
        #         "sql_generated": result_state.generated_sql,
        #         "sql_type": result_state.sql_type,
        #         "requires_human_approval": result_state.requires_human_approval,
        #         "human_approved": result_state.human_approved,
        #         "execution_success": bool(
        #             result_state.sql_execution_result and
        #             result_state.sql_execution_result.get("success")
        #         ),
        #         "row_count": result_state.sql_execution_result.get("row_count", 0)
        #         if result_state.sql_execution_result else 0,
        #         "execution_time": result_state.sql_execution_result.get("execution_time", 0)
        #         if result_state.sql_execution_result else 0,
        #         "error": result_state.sql_error
        #     }
        #
        # except Exception as e:
        #     print(f"❌ 智能体执行异常: {str(e)}")
        #     return {
        #         "answer": f"处理请求时发生错误: {str(e)}",
        #         "session_id": session_id,
        #         "error": str(e)
        #     }


        result_state = self.app.invoke(initial_state, config)
        # 返回结果
        return {
            "answer": result_state["final_answer"],
            "session_id": session_id,
            "sql_generated": result_state["generated_sql"],
            "sql_type": result_state["sql_type"],
            "requires_human_approval": result_state["requires_human_approval"],
            "human_approved": result_state["human_approved"],
            "execution_success": bool(
                result_state["sql_execution_result"] and
                result_state["sql_execution_result"].get("success")
            ),
            "row_count": result_state["sql_execution_result"].get("row_count", 0)
            if result_state["sql_execution_result"] else 0,
            "execution_time": result_state["sql_execution_result"].get("execution_time", 0)
            if result_state["sql_execution_result"] else 0,
            "error": result_state["sql_error"]
        }


    def approve_sql(self, approval_index: int, approve: bool = True, comments: str = "") -> Dict[str, Any]:
        """
        人工审核SQL

        Args:
            approval_index: 审核队列索引
            approve: 是否批准
            comments: 审核意见

        Returns:
            审核结果
        """
        try:
            if approval_index < 0 or approval_index >= len(self.sql_executor.human_approval_queue):
                return {
                    "success": False,
                    "error": f"无效的审核索引: {approval_index}"
                }

            approval_item = self.sql_executor.human_approval_queue[approval_index]

            if approve:
                # 批准执行
                approval_item["state"]["human_approved"] = True
                approval_item["state"]["requires_human_approval"] = False

                # 更新状态
                approved_state = DatabaseGraphState(**approval_item["state"])

                # 继续执行流程
                result = self.app.invoke(approved_state, {
                    "configurable": {"thread_id": approved_state.session_id}
                })

                # 从队列移除
                self.sql_executor.human_approval_queue.pop(approval_index)

                return {
                    "success": True,
                    "action": "approved",
                    "sql": approval_item["sql"],
                    "result": {
                        "answer": result.final_answer,
                        "execution_success": bool(
                            result.sql_execution_result and
                            result.sql_execution_result.get("success")
                        )
                    },
                    "comments": comments
                }
            else:
                # 拒绝执行
                self.sql_executor.human_approval_queue.pop(approval_index)

                return {
                    "success": True,
                    "action": "rejected",
                    "sql": approval_item["sql"],
                    "result": {
                        "answer": f"SQL执行被拒绝: {comments or '未通过人工审核'}"
                    },
                    "comments": comments
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"审核处理异常: {str(e)}"
            }

    def get_pending_approvals(self) -> List[Dict[str, Any]]:
        """获取待审核的SQL列表"""
        return [
            {
                "index": idx,
                "sql": item["sql"],
                "reason": item["reason"],
                "timestamp": item["timestamp"],
                "session_id": item["session_id"]
            }
            for idx, item in enumerate(self.sql_executor.human_approval_queue)
        ]

    def close(self):
        """关闭资源"""
        self.db_manager.close_all_connections()
        print("✅ 数据库智能体资源已关闭")


# ============== 9. 测试函数 ==============

def test_database_agent():
    """测试数据库智能体"""
    print("🧪 测试数据库智能体...")

    # 测试配置 - 这里使用示例连接字符串，实际使用时需要替换
    test_db_connection = os.getenv("TEST_DB_CONNECTION", "sqlite:///:memory:")

    # 创建测试数据库（如果使用SQLite内存数据库）,只有第一次执行的时候需要初始化数据，后续无需进行数据的初始化
    # if "sqlite" in test_db_connection:
    #     _create_test_database(test_db_connection)

    # 创建智能体实例
    agent = DatabaseAgent(test_db_connection)

    # 测试用例
    test_cases = [
        # 表结构查询
        "查看数据库中有哪些表",
        "显示用户表的结构",

        # 简单查询
        "查询用户表中的所有数据",
        "获取最近10条交易记录",

        # 复杂查询
        "统计每个用户的交易总额",
        "查询2023年每个月的交易量",

        # DML操作（需要人工审核）
        "向用户表添加一条新记录",
        "更新用户张三的手机号",
    ]

    session_id = "test_db_session_001"

    for i, question in enumerate(test_cases, 1):
        print(f"\n📋 测试用例 {i}: {question}")

        try:
            result = agent.ask(question, session_id)

            print(f"📤 回答类型: {result.get('sql_type', 'N/A')}")
            print(f"🔧 生成SQL: {result.get('sql_generated', 'N/A')}...")
            print(f"👥 需要人工审核: {result.get('requires_human_approval', False)}")
            print(f"✅ 执行成功: {result.get('execution_success', False)}")
            print(f"📊 返回行数: {result.get('row_count', 0)}")
            print(f"📝 回答摘要: {result.get('answer', 'N/A')}...")
            print("-" * 50)

        except Exception as e:
            print(f"❌ 处理失败: {e}")
            import traceback
            traceback.print_exc()

    # 测试人工审核功能
    print("\n🧪 测试人工审核功能...")
    pending_approvals = agent.get_pending_approvals()
    if pending_approvals:
        print(f"📋 待审核SQL数量: {len(pending_approvals)}")
        for approval in pending_approvals:
            print(f"  索引 {approval['index']}: {approval['sql'][:100]}...")

    # 关闭资源
    agent.close()


def _create_test_database(connection_string: str):
    """创建测试数据库（仅用于演示）"""
    try:
        from sqlalchemy import Table, Column, Integer, String, Float, DateTime, MetaData

        engine = create_engine(connection_string)
        metadata = MetaData()

        # 创建用户表
        users = Table(
            'users', metadata,
            Column('id', Integer, primary_key=True),
            Column('username', String(50), nullable=False),
            Column('email', String(100)),
            Column('phone', String(20)),
            Column('created_at', DateTime)
        )

        # 创建交易表
        transactions = Table(
            'transactions', metadata,
            Column('id', Integer, primary_key=True),
            Column('user_id', Integer),
            Column('amount', Float),
            Column('type', String(20)),
            Column('description', String(200)),
            Column('created_at', DateTime)
        )

        # 创建表
        metadata.create_all(engine)

        # 插入测试数据
        with engine.connect() as conn:
            # 插入用户数据
            conn.execute(users.insert(), [
                {'username': '张三', 'email': 'zhangsan@example.com', 'phone': '13800138000'},
                {'username': '李四', 'email': 'lisi@example.com', 'phone': '13900139000'},
            ])

            # 插入交易数据
            conn.execute(transactions.insert(), [
                {'user_id': 1, 'amount': 1000.0, 'type': '存款', 'description': '工资'},
                {'user_id': 1, 'amount': -200.0, 'type': '取款', 'description': '购物'},
                {'user_id': 2, 'amount': 500.0, 'type': '存款', 'description': '转账'},
            ])

            # 关键：提交事务，让数据持久化
            conn.commit()

        print("✅ 测试数据库创建完成")

    except Exception as e:
        print(f"❌ 创建测试数据库失败: {str(e)}")


if __name__ == "__main__":
    # 设置数据库连接（示例）
    # 实际使用时，请配置正确的数据库连接字符串
    os.environ["TEST_DB_CONNECTION"] = "sqlite:///test_finance.db"

    # 运行测试
    test_database_agent()

# 查看图结构
# if __name__ == "__main__":
#
#     app = build_database_agent()
#
#     png_data = app.get_graph().draw_mermaid_png()
#     with open('graph.png', 'wb') as f:
#         f.write(png_data)
#     print("图像已保存为graph.png")
#     # 可以尝试自动打开文件
#     import webbrowser, os
#
#     webbrowser.open('file://' + os.path.realpath('graph.png'))