"""在线多模态模型客户端：OpenAI 兼容端点（GLM 开放平台等）。

设计要点：
- generate_with_image 以 data-url 附图，适配 GLM-5.3 等多模态模型
- thinking 参数默认禁用（Agent 单步决策要快、输出要干净的 JSON）；
  该字段是 Zhipu 扩展，其他兼容端点可经 ONLINE_THINKING=default 关闭传参
- Agent 路径不依赖 history（上下文由 ContextAssembler 组装进 prompt）
"""
from __future__ import annotations

import base64
import json
import time
from typing import Callable

import httpx

from src.llm.base import BaseLLMClient

# Function Calling 工具声明：工具名 = 动作类型，参数 = ids + 可选 conclusions。
# 与 prompt-json 模式共用同一套解析入口（客户端把 tool_calls 序列化成动作
# JSON 文本），因此两种协议的行为可直接 A/B 对比。
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


class OnlineLLMClient(BaseLLMClient):
    def __init__(self, api_key: str, model: str,
                 base_url: str | None = None, timeout: int = 120,
                 thinking: str = "off", max_tokens: int | None = None,
                 function_calling: bool = False,
                 progress_callback: Callable[[int], None] | None = None,
                 progress_interval_s: float = 30.0):
        if not api_key:
            raise ValueError(
                "缺少在线模型 API Key：请在项目根目录 .env 中设置 "
                "ONLINE_API_KEY（GLM 开放平台 open.bigmodel.cn 获取）")
        self.api_key = api_key
        self.model = model
        self.base_url = (base_url or "https://open.bigmodel.cn/api/paas/v4").rstrip("/")
        self.timeout = timeout
        self.thinking = thinking
        # max_tokens=0/None → 请求不带该字段，服务端用模型输出上限兜底
        # （始终思考型模型推荐：思考量随局面复杂度波动，框架侧设顶会把
        # 思考截断成空答案——token 照计费却没有产出）；正值 = 生成硬顶
        self.max_tokens = max_tokens
        # Function Calling 开关：动作改由 API 层工具声明（硬约束），
        # 返回值仍序列化成动作 JSON 文本，对上层解析器零侵入
        self.function_calling = function_calling
        # 流式进度回调：每隔 interval 秒以"已接收字符数"回调一次，
        # 用于在控制台证明"仍在思考"（长思考 30+ 分钟时不是卡死）。
        # interval<=0 = 每收到一个增量就回调（测试用）
        self.progress_callback = progress_callback
        self.progress_interval_s = progress_interval_s

    # ---------- 请求构造 ----------

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"}

    def _payload(self, messages: list[dict]) -> dict:
        payload: dict = {"model": self.model, "messages": messages, "stream": True}
        if self.max_tokens:
            payload["max_tokens"] = self.max_tokens
        # thinking 配置语义（兼容不同模型）：
        #   off → 关闭思考（部分模型支持）；on → 默认强度开启；
        #   low/high/max → 始终思考型模型（如 glm-5.3-flash）的思考速度档位
        if self.thinking == "off":
            payload["thinking"] = {"type": "disabled"}
        elif self.thinking == "on":
            payload["thinking"] = {"type": "enabled"}
        elif self.thinking in ("low", "high", "max"):
            payload["thinking"] = {"type": "enabled", "speed": self.thinking}
        if self.function_calling:
            payload["tools"] = ACTION_TOOLS
        return payload

    @staticmethod
    def _user_content(prompt: str, images: list[bytes]):
        if not images:
            return prompt  # 纯文本请求用字符串 content，兼容性最好
        parts: list[dict] = [{"type": "text", "text": prompt}]
        for b in images:
            b64 = base64.b64encode(OnlineLLMClient._normalize_image(b)).decode()
            parts.append({"type": "image_url",
                          "image_url": {"url": f"data:image/png;base64,{b64}"}})
        return parts

    def _messages(self, prompt: str, history: list[dict] | None,
                  images: list[bytes] | None = None) -> list[dict]:
        messages = list(history or [])
        messages.append({"role": "user",
                         "content": self._user_content(prompt, images or [])})
        return messages

    # ---------- 请求执行 ----------

    async def _chat(self, messages: list[dict]) -> str:
        # 流式请求 + 心跳式挂死检测：服务端立即持续推送增量（思考阶段推
        # reasoning_content，作答阶段推 content），字节流不断 = 活着。
        # 读超时语义 = "两次字节之间的最大间隔"（ONLINE_TIMEOUT，几十秒）：
        # 服务端间歇性挂起时字节流中断 → 快速超时 → 自动重试一次，无需
        # 等待整个生成周期。max_tokens 与该超时从此解耦（流式下两者都安全）。
        timeout = httpx.Timeout(self.timeout if self.timeout > 0 else None,
                                connect=10.0)
        last_err: Exception | None = None
        for attempt in (1, 2):
            try:
                chunks: list[str] = []
                finish: str | None = None
                tool_calls: dict[int, dict] = {}  # index → {name, arguments}（流式碎片累积）
                received = 0                     # 已接收字符数（含思考增量）
                last_progress = time.monotonic()
                async with httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream(
                            "POST", f"{self.base_url}/chat/completions",
                            headers=self._headers(),
                            json=self._payload(messages)) as resp:
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if not line.startswith("data:"):
                                continue  # SSE 空行/注释行
                            data = line[len("data:"):].strip()
                            if data == "[DONE]":
                                break
                            try:
                                obj = json.loads(data)
                            except json.JSONDecodeError:
                                continue  # 容忍无法解析的心跳行
                            choice = (obj.get("choices") or [{}])[0]
                            delta = choice.get("delta") or {}
                            if delta.get("content"):
                                chunks.append(delta["content"])
                                received += len(delta["content"])
                            # 思考期增量（智谱 reasoning_content）只用于进度显示，
                            # 不进最终答案——它证明服务端仍在生成
                            if delta.get("reasoning_content"):
                                received += len(delta["reasoning_content"])
                            if self.progress_callback and self.progress_interval_s >= 0:
                                now = time.monotonic()
                                if now - last_progress >= self.progress_interval_s:
                                    last_progress = now
                                    try:
                                        self.progress_callback(received)
                                    except Exception:
                                        pass  # 进度回调异常不影响请求
                            for tc in delta.get("tool_calls") or []:
                                slot = tool_calls.setdefault(
                                    tc.get("index", 0),
                                    {"name": "", "arguments": ""})
                                fn = tc.get("function") or {}
                                if fn.get("name"):
                                    slot["name"] += fn["name"]
                                if fn.get("arguments"):
                                    slot["arguments"] += fn["arguments"]
                            if choice.get("finish_reason"):
                                finish = choice["finish_reason"]
                content = "".join(chunks)
                if tool_calls:
                    content = self._merge_tool_calls(content, tool_calls)
                if not content.strip() and finish == "length":
                    raise Exception(
                        "响应被生成长度上限截断且答案为空（finish_reason=length）。"
                        "若 .env 中 ONLINE_MAX_TOKENS>0 可调大或改为 0（不限制）；"
                        "若已为 0 则触达服务端模型输出上限")
                return content
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    raise Exception("API Key 无效或过期（401），请检查 .env 中的 ONLINE_API_KEY")
                raise Exception(f"在线模型请求失败: {e.response.text[:300]}")
            except (KeyError, IndexError) as e:
                raise Exception(f"在线模型响应格式异常: {e}")
            except httpx.HTTPError as e:
                last_err = e
                if attempt == 1:
                    import asyncio
                    await asyncio.sleep(2)  # 瞬时故障/挂死超时，短暂等待后重试
        raise Exception(f"连接在线模型失败（已重试）: {last_err}")

    @staticmethod
    def _merge_tool_calls(content: str, slots: dict[int, dict]) -> str:
        """把流式累积的 tool_calls 序列化成动作 JSON，追加在推理正文之后。

        输出与非 FC 模式同构（{"type","ids","conclusions"}），因此 Runner 的
        parse_action / SoM 编号解析零改动；正文里的推理与结论收集也照常工作。
        多个调用并存时只取最后一个（与 parse_action 的"取末尾终稿"一致，
        保证两种协议的执行语义可比）。
        """
        action: dict | None = None
        for idx in sorted(slots):
            slot = slots[idx]
            name = slot.get("name", "").strip()
            try:
                args = json.loads(slot.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            if name not in ("click", "flag"):
                continue  # 未知工具名直接丢弃，交由解析器报"未找到动作"
            item: dict = {"type": name}
            ids = args.get("ids")
            if isinstance(ids, list) and ids:
                item["ids"] = [str(i) for i in ids]
            elif args.get("id") is not None:
                item["id"] = str(args["id"])
            cons = args.get("conclusions")
            if isinstance(cons, list) and cons:
                item["conclusions"] = [str(c) for c in cons]
            action = item
        if action is None:
            return content
        body = content.rstrip()
        payload = json.dumps(action, ensure_ascii=False)
        return f"{body}\n{payload}" if body else payload

    # ---------- BaseLLMClient 接口 ----------

    async def generate(self, prompt: str, history: list[dict] | None = None) -> str:
        return await self._chat(self._messages(prompt, history))

    @staticmethod
    def _normalize_image(image_bytes: bytes) -> bytes:
        """重编码截图为标准 RGB PNG。

        某些截屏库（mss）产出的 PNG 编码会让部分在线视觉服务挂起
        （请求无响应直至超时，重试无效）；同一图像经 PIL 重编码后立即
        正常。重编码失败时退回原始字节。
        """
        try:
            import io

            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            return image_bytes

    async def generate_with_images(self, prompt: str, images: list[bytes],
                                   history: list[dict] | None = None) -> str:
        return await self._chat(self._messages(prompt, history, images))

    async def stream_generate(self, prompt: str, history: list[dict] | None = None):
        """Agent 路径不使用流式；为接口完整性提供一次性产出。"""
        text = await self.generate(prompt, history)
        yield text
