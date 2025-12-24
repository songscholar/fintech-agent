import time
import logging

from src.dev.state.graph_state import GraphState

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fintech_agent")

# 装饰器：记录节点执行耗时
def log_node_execution(node_func):
    def wrapper(state: GraphState) -> GraphState:
        start_time = time.time()
        try:
            result = node_func(state)
            logger.info(f"节点 {node_func.__name__} 执行成功，耗时：{time.time()-start_time:.2f}s")
            return result
        except Exception as e:
            logger.error(f"节点 {node_func.__name__} 执行失败：{str(e)}，耗时：{time.time()-start_time:.2f}s")
            raise e
    return wrapper