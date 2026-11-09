"""游戏环境自主 Agent 研究框架（v1.0 最小闭环）。

公共出口：
    from src.framework import MockEnv, AgentRunner, make_llm_decider, Task
"""
from src.framework.env.base import Environment
from src.framework.env.mock_env import MockEnv
from src.framework.env.minesweeper_env import MinesweeperEnv
from src.framework.env.virtual_minesweeper_env import VirtualMinesweeperEnv
from src.framework.env.window_env import WindowEnv
from src.framework.history import HistoryManager
from src.framework.human_decider import HumanDecider
from src.framework.llm_adapter import make_llm_decider
from src.framework.perception import Perception
from src.framework.runner import AgentRunner, RunResult
from src.framework.run_trace import RunTraceLogger
from src.framework.types import (
    ACTION_SCHEMA_HINT,
    Action,
    ActionParseError,
    Element,
    FrameAnalysis,
    Status,
    Task,
    parse_action,
)

__all__ = [
    "Environment", "MockEnv", "WindowEnv", "MinesweeperEnv",
    "VirtualMinesweeperEnv", "AgentRunner", "RunResult", "HumanDecider",
    "RunTraceLogger",
    "Perception", "HistoryManager", "make_llm_decider",
    "Action", "ActionParseError", "parse_action", "ACTION_SCHEMA_HINT",
    "Element", "FrameAnalysis", "Task", "Status",
]
