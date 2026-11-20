"""Agent 循环与运行时：扫雷 benchmark 的执行核心（v1.0）。

公共出口：
    from game_agent.framework import MockEnv, AgentRunner, make_llm_decider, Task
"""
from game_agent.framework.env.base import Environment
from game_agent.framework.env.mock_env import MockEnv
from game_agent.framework.env.minesweeper_env import MinesweeperEnv
from game_agent.framework.env.virtual_minesweeper_env import VirtualMinesweeperEnv
from game_agent.framework.env.window_env import WindowEnv
from game_agent.framework.history import HistoryManager
from game_agent.framework.human_decider import HumanDecider
from game_agent.framework.llm_adapter import make_llm_decider
from game_agent.framework.perception import Perception
from game_agent.framework.runner import AgentRunner, RunResult
from game_agent.framework.run_trace import RunTraceLogger
from game_agent.framework.types import (
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
