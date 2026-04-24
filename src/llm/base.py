from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    @abstractmethod
    async def generate(self, prompt: str, history: list[dict] | None = None) -> str:
        pass

    @abstractmethod
    async def generate_with_image(self, prompt: str, image_bytes: bytes, history: list[dict] | None = None) -> str:
        pass

    @abstractmethod
    async def stream_generate(self, prompt: str, history: list[dict] | None = None):
        pass
