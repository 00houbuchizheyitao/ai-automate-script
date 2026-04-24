import pytest

from src.llm.ollama_client import OllamaClient
from src.config.settings import AppSettings


@pytest.fixture
def settings():
    return AppSettings()


@pytest.fixture
def ollama_client(settings):
    return OllamaClient(settings)


class TestOllamaClient:
    def test_client_init(self, ollama_client):
        assert ollama_client is not None
        assert ollama_client.model == "qwen2.5-vl:7b"

    def test_build_messages(self, ollama_client):
        messages = ollama_client._build_messages("hello")
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "hello"

    def test_build_messages_with_history(self, ollama_client):
        history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
        messages = ollama_client._build_messages("new message", history)
        assert len(messages) == 3
