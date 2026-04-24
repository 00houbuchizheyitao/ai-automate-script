from src.llm.base import BaseLLMClient


class OnlineLLMClient(BaseLLMClient):
    """
    在线大模型客户端（未来实现）
    支持 OpenAI / Claude / Gemini 等在线 API
    """

    def __init__(self, api_key: str, model: str, base_url: str | None = None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url

    async def generate(self, prompt: str, history: list[dict] | None = None) -> str:
        raise NotImplementedError("在线大模型客户端尚未实现")

    async def generate_with_image(self, prompt: str, image_bytes: bytes, history: list[dict] | None = None) -> str:
        raise NotImplementedError("在线大模型客户端尚未实现")

    async def stream_generate(self, prompt: str, history: list[dict] | None = None):
        raise NotImplementedError("在线大模型客户端尚未实现")
        yield
