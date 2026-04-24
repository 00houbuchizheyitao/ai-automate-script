import pytest

from src.agent.agent import Agent
from src.config.settings import AppSettings


@pytest.fixture
def settings():
    return AppSettings()


@pytest.fixture
def agent(settings):
    return Agent(settings)


class TestAgent:
    def test_agent_init(self, agent):
        assert agent is not None
        assert agent.conversation_history == []

    def test_clear_history(self, agent):
        agent.conversation_history.append({"role": "user", "content": "test"})
        agent.clear_history()
        assert agent.conversation_history == []

    def test_build_prompt(self, agent):
        prompt = agent._build_prompt("打开记事本")
        assert "打开记事本" in prompt
        assert "pyautogui" in prompt
