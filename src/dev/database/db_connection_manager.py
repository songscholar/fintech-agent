from typing import Dict, Any, List
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.exc import SQLAlchemyError

class DatabaseConnectionManager:
    """数据库连接管理器 - 支持多种数据库类型"""

    def __init__(self):
        self.connections = {}
        self.metadata_cache = {}

    def create_connection(self, connection_string: str, alias: str = "default") -> Any:
        """
        创建数据库连接

        Args:
            connection_string: 数据库连接字符串
            alias: 连接别名

        Returns:
            SQLAlchemy engine对象
        """
        try:
            # 创建连接池
            engine = create_engine(
                connection_string,
                pool_size=5,
                max_overflow=10,
                pool_recycle=3600,
                pool_pre_ping=True,
                echo=False  # 生产环境设为False
            )

            # 测试连接
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))

            self.connections[alias] = engine
            print(f"✅ 数据库连接成功: {alias}")
            return engine

        except SQLAlchemyError as e:
            print(f"❌ 数据库连接失败: {str(e)}")
            raise

    def get_table_metadata(self, engine, table_names: List[str] = None) -> Dict[str, Any]:
        """
        获取表结构元数据

        Args:
            engine: 数据库引擎
            table_names: 表名列表，None表示获取所有表

        Returns:
            表结构元数据
        """
        cache_key = f"{engine.url}_{table_names}"
        if cache_key in self.metadata_cache:
            return self.metadata_cache[cache_key]

        metadata = {
            "tables": {},
            "relationships": [],
            "statistics": {}
        }

        try:
            inspector = inspect(engine)

            # 获取所有表名
            all_tables = inspector.get_table_names()
            if table_names:
                target_tables = [t for t in table_names if t in all_tables]
            else:
                target_tables = all_tables

            for table_name in target_tables:
                table_info = {
                    "columns": [],
                    "primary_keys": inspector.get_pk_constraint(table_name),
                    "foreign_keys": inspector.get_foreign_keys(table_name),
                    "indexes": inspector.get_indexes(table_name),
                    "row_count": self._get_table_row_count(engine, table_name)
                }

                # 获取列信息
                columns = inspector.get_columns(table_name)
                for column in columns:
                    column_info = {
                        "name": column["name"],
                        "type": str(column["type"]),
                        "nullable": column.get("nullable", True),
                        "default": column.get("default"),
                        "comment": column.get("comment", "")
                    }
                    table_info["columns"].append(column_info)

                metadata["tables"][table_name] = table_info

            # 缓存元数据
            self.metadata_cache[cache_key] = metadata
            return metadata

        except Exception as e:
            print(f"❌ 获取表元数据失败: {str(e)}")
            return metadata

    def _get_table_row_count(self, engine, table_name: str) -> int:
        """获取表行数"""
        try:
            with engine.connect() as conn:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                return result.scalar()
        except:
            return 0

    def close_all_connections(self):
        """关闭所有数据库连接"""
        for alias, engine in self.connections.items():
            try:
                engine.dispose()
                print(f"✅ 关闭数据库连接: {alias}")
            except:
                pass
        self.connections.clear()
