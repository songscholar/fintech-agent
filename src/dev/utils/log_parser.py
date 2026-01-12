import re
import json
from typing import Dict, Any, Optional


class UniversalLogParser:
    """
    企业级通用日志解析器
    支持格式：
    1. C++ BizLog (格式: 1126 165301.529458 120 ERROR ...)
    2. Java Error Log (格式: 2026-01-08 16:20:00.012 |-ERROR ...)
    """

    # --- C++ BizLog Regex ---
    # 示例: 1126 165301.529458   120 ERROR 2470961 2471857 03972d... [120][业务包为空]...
    _CPP_PATTERN = re.compile(
        r"^(\d{4})\s+(\d{6}\.\d{6})\s+(\d+)\s+([A-Z]+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(.+)$"
    )

    # --- Java Error Log Regex ---
    # 示例: 2026-01-08 16:20:00.012 |-ERROR [Thread-1] [] [T11...] com.xxx.Log [] -|{"type":...}
    _JAVA_PATTERN = re.compile(
        r"^(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}\.\d{3})\s+\|-([A-Z]+)\s+\[(.*?)\]\s+\[(.*?)\]\s+\[(.*?)\]\s+(\S+)\s+\[(.*?)\]\s+-\|(.*)$",
        re.DOTALL
    )

    @classmethod
    def parse(cls, text: str) -> Dict[str, Any]:
        """
        解析日志文本（支持多行输入）
        :param text: 用户输入的完整日志片段
        :return: 结构化字典，包含 log_type, error_code, summary 等关键字段
        """
        text = text.strip()
        if not text:
            return cls._create_fallback("EMPTY_INPUT", "输入为空")

        # 1. 预处理：智能定位 Header 行
        lines = text.split('\n')
        header_line = ""
        # 扫描前5行，寻找符合特征的头部
        for line in lines[:5]:
            if line.strip():
                header_line = line.strip()
                break

        if not header_line:
            return cls._create_fallback("UNKNOWN_FORMAT", text[:200])

        # 2. 尝试匹配 Java 格式 (特征: 日期开头 + |-LEVEL)
        java_match = cls._JAVA_PATTERN.match(header_line)
        if java_match:
            return cls._parse_java_log(java_match, text)

        # 3. 尝试匹配 C++ 格式 (特征: MMDD开头)
        cpp_match = cls._CPP_PATTERN.match(header_line)
        if cpp_match:
            return cls._parse_cpp_log(cpp_match)

        # 4. 无法识别，返回兜底结构
        return cls._create_fallback("UNKNOWN_FORMAT", text[:200])

    @classmethod
    def _parse_cpp_log(cls, match: re.Match) -> Dict[str, Any]:
        """解析 C++ 日志"""
        groups = match.groups()
        raw_message = groups[7]

        # 尝试从消息体中提取源码位置 (例如: src/trans_ctrl_impl.cpp:1545)
        # 这种源码位置是 RAG 检索的黄金关键词
        source_loc = "UNKNOWN"
        loc_match = re.search(r"((?:src|uft|components)/[\w\./_]+\.(?:cpp|cc|h):\d+)", raw_message)
        if loc_match:
            source_loc = loc_match.group(1)

        return {
            "success": True,
            "log_type": "CPP_BIZ_LOG",
            "timestamp": f"{groups[0]} {groups[1]}",  # MMDD HHMMSS
            "level": groups[3],
            "error_code": groups[2],
            "component": source_loc,  # 用源码文件作为组件标识
            "summary": raw_message[:300],  # 截取前300字符作为摘要
            "details": {
                "pid": groups[4],
                "tid": groups[5],
                "stack_addr": groups[6],
                "full_message": raw_message
            }
        }

    @classmethod
    def _parse_java_log(cls, match: re.Match, full_text: str) -> Dict[str, Any]:
        """解析 Java 日志"""
        groups = match.groups()
        # Header 行中捕获的 Message 部分（通常是 JSON 的开始）
        header_msg_part = groups[7].strip()

        parsed = {
            "success": True,
            "log_type": "JAVA_ERROR_LOG",
            "timestamp": groups[0],
            "level": groups[1],
            "trace_id": groups[4],
            "component": groups[5],  # 默认组件：Logger 类名
            "error_code": "N/A",
            "summary": "Java Error",
            "details": {}
        }

        # --- JSON 提取逻辑 ---
        # Java 日志结构通常是: Header -| JSON字符串 \n 堆栈...
        try:
            # 在整个文本中寻找 JSON 对象
            start_idx = full_text.find('{')
            end_idx = full_text.rfind('}')

            if start_idx != -1 and end_idx != -1 and start_idx < end_idx:
                json_str = full_text[start_idx: end_idx + 1]
                json_data = json.loads(json_str)

                parsed["details"]["json_payload"] = json_data

                # 提取业务错误码 (myPackage.error_no)
                if "myPackage" in json_data:
                    pkg = json_data["myPackage"]
                    parsed["error_code"] = str(pkg.get("error_no", "N/A"))

                    # 提取更详细的错误摘要
                    err_info = pkg.get("error_info", "")
                    if "origin_message=" in err_info:
                        # 尝试切片提取: origin_message=xxx;
                        try:
                            # 简单的文本切割提取
                            origin_msg = err_info.split("origin_message=")[1].split(";")[0]
                            parsed["summary"] = origin_msg
                        except IndexError:
                            parsed["summary"] = err_info[:200]
                    else:
                        parsed["summary"] = err_info[:200] if err_info else parsed["summary"]

                    # 尝试从 class_name 优化组件名
                    if "class_name=" in err_info:
                        cn_match = re.search(r"class_name=([\w\.]+)", err_info)
                        if cn_match:
                            # 只取类名简写，如 SysTimeDAOImpl
                            parsed["component"] = cn_match.group(1).split('.')[-1]

        except (json.JSONDecodeError, IndexError):
            # JSON 解析失败不应阻塞整体流程
            parsed["summary"] = header_msg_part[:200]

        # --- 堆栈与异常提取 ---
        # 如果 JSON 没提取到有用的 Summary，尝试从堆栈中提取 Exception 类名
        if parsed["summary"] == "Java Error" or not parsed["summary"]:
            # 匹配 "xxxException: message"
            ex_match = re.search(r"([\w\.]+(?:Exception|Error)): (.*)", full_text)
            if ex_match:
                parsed["summary"] = f"{ex_match.group(1).split('.')[-1]}: {ex_match.group(2)[:100]}"

        # 保存完整堆栈供 LLM 参考
        parsed["details"]["full_stack_trace"] = full_text

        return parsed

    @classmethod
    def _create_fallback(cls, log_type: str, summary: str) -> Dict[str, Any]:
        """构建兜底的返回结构"""
        return {
            "success": False,
            "log_type": log_type,
            "error_code": "UNKNOWN",
            "component": "UNKNOWN",
            "summary": summary,
            "details": {}
        }