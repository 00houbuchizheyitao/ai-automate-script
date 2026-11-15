"""动作协议共享定义：工具声明与 tool_calls 归一化。

在线端与 Ollama 端共用同一套动作语义，避免任一客户端反向依赖另一个：
- ACTION_TOOLS：Function Calling 的工具声明
- merge_tool_calls：把 OpenAI / Ollama 的 tool_calls 转成动作 JSON 文本
"""
from __future__ import annotations

import json
from typing import Any

# 工具名 = 动作类型，参数 = ids + 可选 conclusions。
# 与 prompt-json 模式共用同一套解析入口（客户端把 tool_calls 序列化成
# 动作 JSON 文本），因此两种协议的行为可直接 A/B 对比。
ACTION_TOOLS: list[dict] = [
    {"type": "function", "function": {
        "name": "click",
        "description": "翻开一个或多个未翻开的格子（扫雷）。编号见 SoM 序号图。",
        "parameters": {
            "type": "object",
            "properties": {
                "ids": {"type": "array", "items": {"type": "string"},
                        "description": "要翻开的格子编号，如 [\"30\", \"70\"]"},
                "conclusions": {
                    "type": "array", "items": {"type": "string"},
                    "description": "可选：值得下一步复用的推理结论（如某几格恰含一雷）"},
            },
            "required": ["ids"],
        },
    }},
    {"type": "function", "function": {
        "name": "flag",
        "description": "标记一个或多个确定是雷的格子。编号见 SoM 序号图。",
        "parameters": {
            "type": "object",
            "properties": {
                "ids": {"type": "array", "items": {"type": "string"},
                        "description": "要标记的雷格编号"},
                "conclusions": {
                    "type": "array", "items": {"type": "string"},
                    "description": "可选：值得下一步复用的推理结论"},
            },
            "required": ["ids"],
        },
    }},
]


def _arguments_dict(arguments: Any) -> dict:
    """兼容 OpenAI（JSON 字符串）与 Ollama（对象）两种 arguments 形态。"""
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def action_from_tool_call(name: str, arguments: Any) -> dict | None:
    """把一个 tool call 归一化为框架动作；未知工具名返回 None。"""
    name = (name or "").strip()
    if name not in ("click", "flag"):
        return None
    args = _arguments_dict(arguments)
    item: dict = {"type": name}
    ids = args.get("ids")
    if isinstance(ids, str) and ids:
        item["ids"] = [ids]
    elif isinstance(ids, list) and ids:
        item["ids"] = [str(i) for i in ids]
    elif args.get("id") is not None:
        item["id"] = str(args["id"])
    cons = args.get("conclusions")
    if isinstance(cons, list) and cons:
        item["conclusions"] = [str(c) for c in cons]
    return item


def merge_tool_calls(content: str, tool_calls: list[dict]) -> str:
    """把 tool_calls 序列化成动作 JSON，追加在推理正文之后。

    多个调用并存时只取最后一个，与 parse_action 的"取末尾终稿"一致，
    保证两种动作协议的执行语义可比。
    """
    action: dict | None = None
    for tc in tool_calls:
        fn = tc.get("function") or {}
        item = action_from_tool_call(fn.get("name", ""), fn.get("arguments"))
        if item is not None:
            action = item
    if action is None:
        return content
    body = content.rstrip()
    payload = json.dumps(action, ensure_ascii=False)
    return f"{body}\n{payload}" if body else payload
