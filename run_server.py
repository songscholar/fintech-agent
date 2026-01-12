import uvicorn
import os
import sys

# 将当前目录加入 Python 路径，确保能找到 src 包
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    print("🔥 正在启动日志分析后端服务...")
    print("📝 文档地址: http://localhost:8000/docs")

    # 启动 Uvicorn 服务器
    # reload=True 表示代码修改后自动重启，适合开发阶段
    uvicorn.run("src.dev.api.server:app", host="0.0.0.0", port=8000, reload=True)