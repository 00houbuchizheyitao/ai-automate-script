"""LLM 客户端抽象与能力声明。

Runner 只依赖 generate_with_images 的文本结果；能力声明用于在启动时
快速失败，避免"模型不支持视觉/工具调用"到运行中途才暴露。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMCapabilities:
    """客户端传输层支持的能力（不代表某个具体模型一定具备）。"""

    vision: bool = False
    function_calling: bool = False
    streaming: bool = False


class CapabilityError(RuntimeError):
    """客户端缺少调用方要求的能力。"""


def ensure_capabilities(client: "BaseLLMClient", *, vision: bool = False,
                        function_calling: bool = False) -> None:
    caps = client.capabilities
    missing = []
    if vision and not caps.vision:
        missing.append("vision")
    if function_calling and not caps.function_calling:
        missing.append("function_calling")
    if missing:
        raise CapabilityError(
            f"{type(client).__name__} 缺少所需能力: {', '.join(missing)}")


class BaseLLMClient(ABC):
    @property
    @abstractmethod
    def capabilities(self) -> LLMCapabilities:
        """客户端支持的能力；调用方据此在启动时校验。"""

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
