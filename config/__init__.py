import os
import yaml
from pathlib import Path
from typing import Any, Optional
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


class Config:
    """配置管理器（单例）"""
    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """初始化配置"""
        self.base_dir = Path(__file__).parent.parent

        # 确定当前环境
        # todo
        self.env = os.getenv('APP_ENV', 'development').lower()

        # 加载配置
        self._load_configs()

    def _load_configs(self):
        """加载所有配置文件"""
        config_dir = self.base_dir / 'config'

        # 1. 加载基础配置
        base_config = config_dir / 'config.yaml'
        self._config = self._load_yaml(base_config)

        # 2. 加载环境特定配置
        env_config = config_dir / f'settings_{self.env}.yaml'
        if env_config.exists():
            env_data = self._load_yaml(env_config)
            self._merge_dicts(self._config, env_data)

        # 3. 用环境变量覆盖配置
        self._override_with_env_vars()

    def _load_yaml(self, filepath: Path) -> dict:
        """加载YAML文件"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"加载配置文件失败: {filepath}, 错误: {e}")
            return {}

    def _merge_dicts(self, base: dict, override: dict):
        """递归合并字典"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_dicts(base[key], value)
            else:
                base[key] = value

    def _override_with_env_vars(self):
        """用环境变量覆盖配置"""
        # 数据库配置
        if os.getenv('DB_HOST'):
            self._config['database']['host'] = os.getenv('DB_HOST')
        if os.getenv('DB_PORT'):
            self._config['database']['port'] = int(os.getenv('DB_PORT'))
        if os.getenv('DB_USER'):
            self._config['database']['username'] = os.getenv('DB_USER')
        if os.getenv('DB_PASSWORD'):
            self._config['database']['password'] = os.getenv('DB_PASSWORD')
        if os.getenv('DB_NAME'):
            self._config['database']['name'] = os.getenv('DB_NAME')

        # Redis配置
        if os.getenv('REDIS_PASSWORD'):
            self._config['redis']['password'] = os.getenv('REDIS_PASSWORD')

        # 应用配置
        if os.getenv('SECRET_KEY'):
            self._config['app']['secret_key'] = os.getenv('SECRET_KEY')
        if os.getenv('DEBUG'):
            self._config['app']['debug'] = os.getenv('DEBUG').lower() == 'true'
        if os.getenv('PORT'):
            self._config['app']['port'] = int(os.getenv('PORT'))

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        示例: cfg.get('database.host')
        """
        keys = key.split('.')
        value = self._config

        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def reload(self):
        """重新加载配置"""
        self._load_configs()

    def get_database_url(self) -> str:
        """获取数据库连接URL"""
        db = self._config['database']
        username = db.get('username', '')
        password = db.get('password', '')
        host = db.get('host', 'localhost')
        port = db.get('port', 5432)
        name = db.get('name', '')

        if username and password:
            return f"postgresql://{username}:{password}@{host}:{port}/{name}"
        else:
            return f"postgresql://{host}:{port}/{name}"

    def get_redis_url(self) -> str:
        """获取Redis连接URL"""
        redis = self._config['redis']
        host = redis.get('host', 'localhost')
        port = redis.get('port', 6379)
        password = redis.get('password', '')
        db = redis.get('db', 0)

        if password:
            return f"redis://:{password}@{host}:{port}/{db}"
        else:
            return f"redis://{host}:{port}/{db}"

    @property
    def data(self) -> dict:
        """获取所有配置数据"""
        return self._config.copy()

    def __getitem__(self, key: str) -> Any:
        """支持字典式访问"""
        return self.get(key)


# 创建全局配置实例
config = Config()