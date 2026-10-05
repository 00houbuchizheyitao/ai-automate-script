from abc import ABC, abstractmethod


class BaseLLMClient(ABC):
    @abstractmethod
    async def generate(self, prompt: str, history: list[dict] | None = None) -> str:
        pass

    @abstractmethod
    async def generate_with_images(self, prompt: str, images: list[bytes],
                                   history: list[dict] | None = None) -> str:
        """多图版本：Agent 的 SoM 场景会同时发送原图与标注图。"""
        pass

    async def generate_with_image(self, prompt: str, image_bytes: bytes,
                                  history: list[dict] | None = None) -> str:
        """单图便捷方法（兼容旧调用），委托给多图版本。"""
        return await self.generate_with_images(prompt, [image_bytes], history)

    @abstractmethod
    async def stream_generate(self, prompt: str, history: list[dict] | None = None):
        pass
