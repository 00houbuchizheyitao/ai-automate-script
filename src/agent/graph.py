from src.agent.agent import Agent


class AgentGraph:
    """
    LangGraph 工作流定义（MVP 阶段预留，未来实现）

    工作流节点:
    1. understand   - 理解用户意图（截图 + 文本）
    2. analyze      - 分析截图元素和布局
    3. plan         - 规划脚本执行步骤
    4. generate     - 生成自动化脚本
    5. validate     - 校验脚本可行性
    6. refine       - 根据校验结果修正脚本（循环回 generate）
    """

    def __init__(self, agent: Agent):
        self.agent = agent

    def build_graph(self):
        pass

    async def run(self, user_input: str, image_bytes: bytes | None = None):
        pass
