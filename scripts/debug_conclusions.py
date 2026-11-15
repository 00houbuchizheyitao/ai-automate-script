"""调试：复现 conclusions 报错（保留用于验证 RunTraceLogger 接入）"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game_agent.framework import AgentRunner, MockEnv, Task


async def decider(prompt, images):
    return '{"type": "click", "id": "5", "conclusions": ["x"]}'


env = MockEnv(seed=1)
env.set_target(100, 100)
runner = AgentRunner(env=env, decider=decider, step_interval_s=0)
r = asyncio.run(runner.run(Task(goal="g", timeout_steps=5)))
print("type:", type(r))
print("has conclusions:", hasattr(r, "conclusions"))
print("status:", r.status, "steps:", r.steps, "conclusions:", getattr(r, "conclusions", None))
