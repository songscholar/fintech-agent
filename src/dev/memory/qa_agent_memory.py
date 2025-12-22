from typing import Dict, List
import json

class MemoryManager:
    """会话记忆管理器，支持多种存储方式"""

    def __init__(self, storage_type: str = "memory", max_turns: int = 10):
        """
        初始化记忆管理器
        Args:
            storage_type: 存储类型，支持 "memory", "redis", "file"
            max_turns: 最大对话轮次
        """
        self.storage_type = storage_type
        self.max_turns = max_turns
        self.memories = {}

        if storage_type == "redis":
            # 这里可以扩展Redis连接
            pass
        elif storage_type == "file":
            self.memory_file = "session_memories.json"

    def get_session_key(self, session_id: str) -> str:
        """生成会话键"""
        return f"session_{session_id}"

    def load_memory(self, session_id: str) -> List[Dict]:
        """加载会话记忆"""
        key = self.get_session_key(session_id)

        if self.storage_type == "memory":
            return self.memories.get(key, [])
        elif self.storage_type == "file":
            try:
                with open(self.memory_file, 'r') as f:
                    all_memories = json.load(f)
                    return all_memories.get(key, [])
            except FileNotFoundError:
                return []
        return []

    def save_memory(self, session_id: str, memory: Dict):
        """保存会话记忆"""
        key = self.get_session_key(session_id)
        memories = self.load_memory(session_id)

        # 只保留最近 max_turns 轮对话
        memories.append(memory)
        if len(memories) > self.max_turns:
            memories = memories[-self.max_turns:]

        if self.storage_type == "memory":
            self.memories[key] = memories
        elif self.storage_type == "file":
            try:
                with open(self.memory_file, 'r') as f:
                    all_memories = json.load(f)
            except FileNotFoundError:
                all_memories = {}

            all_memories[key] = memories

            with open(self.memory_file, 'w') as f:
                json.dump(all_memories, f, indent=2)