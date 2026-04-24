import base64

import httpx

from src.config.settings import AppSettings
from src.llm.base import BaseLLMClient


class OllamaClient(BaseLLMClient):
    def __init__(self, settings: AppSettings):
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.model = settings.OLLAMA_MODEL
        self.timeout = settings.OLLAMA_TIMEOUT

    async def generate(self, prompt: str, history: list[dict] | None = None) -> str:
        messages = self._build_messages(prompt, history)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": False,
                    },
                )
                response.raise_for_status()
                return response.json()["message"]["content"]
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise Exception(f"Ollama 模型 '{self.model}' 未找到或 API 路径错误 (404)。请确保已运行 `ollama pull {self.model}`")
                raise Exception(f"Ollama 请求失败: {e.response.text}")
            except Exception as e:
                raise Exception(f"连接 Ollama 失败: {str(e)}")

    async def generate_with_image(self, prompt: str, image_bytes: bytes, history: list[dict] | None = None) -> str:
        messages = self._build_messages(prompt, history)
        image_b64 = base64.b64encode(image_bytes).decode()

        messages[-1]["images"] = [image_b64]

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": False,
                    },
                )
                response.raise_for_status()
                return response.json()["message"]["content"]
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise Exception(f"Ollama 模型 '{self.model}' 未找到或 API 路径错误 (404)。请确保已运行 `ollama pull {self.model}`")
                raise Exception(f"Ollama 请求失败: {e.response.text}")
            except Exception as e:
                raise Exception(f"连接 Ollama 失败: {str(e)}")

    async def stream_generate(self, prompt: str, history: list[dict] | None = None):
        messages = self._build_messages(prompt, history)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": True,
                    },
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line.strip():
                            import json
                            chunk = json.loads(line)
                            if "message" in chunk:
                                yield chunk["message"].get("content", "")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    raise Exception(f"Ollama 模型 '{self.model}' 未找到或 API 路径错误 (404)。")
                raise Exception(f"Ollama 流式请求失败: {e.response.text}")
            except Exception as e:
                raise Exception(f"连接 Ollama 失败: {str(e)}")

    @staticmethod
    def _build_messages(prompt: str, history: list[dict] | None = None) -> list[dict]:
        messages = []
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})
        return messages
