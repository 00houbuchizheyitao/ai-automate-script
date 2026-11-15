"""框架最小闭环冒烟测试：脚本化决策器 + MockEnv，不依赖 Ollama / 显示器。

跑法：pytest tests/test_framework_loop.py -v
"""
import asyncio
import json

import pytest

from game_agent.framework import (
    Action,
    ActionParseError,
    AgentRunner,
    Element,
    FrameAnalysis,
    MockEnv,
    Status,
    Task,
    parse_action,
)


def test_parse_id_action():
    """SoM 编号动作：id 与 x/y 二选一；id 转字符串；ids 多目标；conclusions 透传"""
    a = parse_action('{"type": "click", "id": 23}')
    assert a.id == "23" and a.x is None and a.y is None
    assert a.describe() == "click(id:23)"

    m = parse_action('{"type": "flag", "ids": [5, 6]}')
    assert m.ids == ("5", "6")

    c = parse_action('{"type": "click", "id": 7, "conclusions": ["雷在8或26"]}')
    assert c.conclusions == ("雷在8或26",)

    f = parse_action('{"type": "flag", "id": 3}')   # flag 单 id 合法
    assert f.type == "flag" and f.id == "3"

    with pytest.raises(ActionParseError, match="id/ids"):
        parse_action('{"type": "flag"}')            # flag 无目标 → 拒绝（Issue2）


def test_mock_env_hit_and_miss():
    env = MockEnv(seed=7)
    env.set_target(400, 300)
    task = Task(goal="点击白色方块", timeout_steps=10)

    env.act(Action(type="click", x=100, y=100))
    assert env.check(task) is Status.RUNNING

    env.act(Action(type="click", x=400, y=300))
    assert env.check(task) is Status.SUCCESS


def test_parse_action_variants():
    assert parse_action('{"type": "click", "x": 10, "y": 20}').describe() == "click(10,20)"
    assert parse_action('废话 {"type":"key","key":"space"} 后缀').describe() == "key(space)"
    assert parse_action('{"type":"wait","ms":250}').describe() == "wait(250ms)"

    # 坐标越界裁剪
    a = parse_action('{"type":"click","x":9999,"y":-5}', screen_size=(800, 600))
    assert (a.x, a.y) == (799, 0)

    with pytest.raises(ActionParseError):
        parse_action("没有任何json")
    with pytest.raises(ActionParseError):
        parse_action('{"type":"fly"}')


def test_parse_action_skips_nonjson_braces():
    """正文推理里的集合记号 {1, 10} 不是 JSON——解析必须越过它找到文末动作。

    回归来源：真实闭环第 3 步，LLM 回复正文含 {31, 32, 33} 等集合记号，
    旧解析器抓第一个片段判死，文末合法的 ids 动作从未被解析（GLM 误报重试）。
    """
    raw = ("## 局面分析\n"
           "41号格周围 {31, 32, 33, 40, 42, 49, 50, 51} 中恰好有1颗雷；"
           "{1, 10} 中恰有1雷，{7, 16} 中恰有1雷。\n"
           "## 行动\n```json\n"
           '{"type": "click", "ids": ["19", "25", "40", "42"], '
           '"conclusions": ["19、25 必安全", "{31,32,33} 中恰有1颗雷"]}\n```\n')
    a = parse_action(raw)
    assert a.describe() == "click(ids:19,25,40,42)"
    assert a.conclusions == ("19、25 必安全", "{31,32,33} 中恰有1颗雷")


def test_parse_action_collects_split_conclusions():
    """conclusions 与动作分离成两个 JSON 对象发回时也要收集到（GLM 实际行为）"""
    raw = ('**行动：**\n```json\n{"type": "click", "id": "5"}\n```\n'
           '**推理结论：**\n```json\n'
           '{"conclusions": ["这8格中恰有1颗雷", "这8格中恰有1颗雷"]}\n```')
    a = parse_action(raw)
    assert a.id == "5"
    assert a.conclusions == ("这8格中恰有1颗雷",)  # 重复结论去重


def test_parse_action_ignores_conclusion_typed_object():
    """结论块自带非法 type 字段时不得被误认成动作（真实闭环第 2/4 步回归）。

    GLM 有时发 {"type": "conclusions", "conclusions": [...]}——若按"含 type
    即动作"处理，排在末尾的结论块会覆盖前面的合法 click，报"未知动作类型"。
    """
    raw = ('## 行动\n{"type": "click", "id": "50"}\n'
           '## 结论传递\n'
           '{"type": "conclusions", "conclusions": ["41=1，8邻格恰1雷"]}\n')
    a = parse_action(raw)
    assert a.id == "50"
    assert a.conclusions == ("41=1，8邻格恰1雷",)


def test_parse_action_collects_bare_conclusion_formats():
    """三种非对象形态的结论都要收集（真实闭环 6 步通关轮的实况回归）。

    GLM 的结论输出格式随机变化：对象形态能收集，裸键值/带引号键值/
    标题后裸数组三种形态此前全部静默丢失（该轮 6 步丢了 3 步的结论）。
    """
    # 形态1：裸键值（第 2 步实况）
    a = parse_action('# 行动\n{"type": "click", "id": "59"}\n\n# 结论\n'
                     'conclusions: ["41周围8格中恰有1颗雷", "选59兼顾信息与连锁"]\n')
    assert a.id == "59"
    assert a.conclusions == ("41周围8格中恰有1颗雷", "选59兼顾信息与连锁")

    # 形态2：结论标题后的裸数组（第 4 步实况，元素含花括号记号）
    a = parse_action('## 结论\n["局面：41=1", "约束：{31,32,33,40,49,50,51}恰1雷"]\n'
                     '## 行动\n{"type": "click", "id": "31"}\n')
    assert a.id == "31"
    assert a.conclusions == ("局面：41=1", "约束：{31,32,33,40,49,50,51}恰1雷")

    # 形态3：带引号键值、无花括号包裹（第 6 步实况；ids 数组不得误收）
    a = parse_action('{"type": "click", "ids": ["20", "21"]}\n\n# 传回结论\n\n'
                     '"conclusions": ["29是雷", "20安全"]\n')
    assert a.ids == ("20", "21")
    assert a.conclusions == ("29是雷", "20安全")


def test_prompt_only_includes_last_step_conclusions():
    """结论注入只带上一步的结论——早期结论对当前局面已过时（用户实测反馈）。

    结论注入是 SoM 三段结构的行为；RunResult.conclusions 仍全量累积。
    """
    class TaggedEnv(MockEnv):
        """MockEnv + 静态 tags：触发 SoM 极简模式（结论注入只在该模式生效）"""

        def capture(self):
            frame = super().capture()
            return type(frame)(screenshot=frame.screenshot, elements=frame.elements,
                               notes=frame.notes, tags={"1": (10, 10)})

    env = TaggedEnv(seed=1)
    env.set_target(500, 200)
    prompts: list[str] = []

    async def decider(prompt: str, images: list) -> str:
        prompts.append(prompt)
        n = len(prompts)
        x, y = (500, 200) if n == 3 else (10, 10)  # 前两步脱靶，第 3 步命中
        return json.dumps({"type": "click", "x": x, "y": y,
                           "conclusions": [f"第{n}步结论"]})

    runner = AgentRunner(env=env, decider=decider, step_interval_s=0)
    result = asyncio.run(runner.run(Task(goal="点击白色方块", timeout_steps=5)))

    assert result.status.value == "success"
    assert "上一步推理结论" not in prompts[0]                            # 第 1 步无结论段
    assert "第1步结论" in prompts[1] and "第2步结论" not in prompts[1]   # 步 2 只见步 1 的
    assert "第2步结论" in prompts[2] and "第1步结论" not in prompts[2]   # 步 3 只见步 2 的
    assert result.conclusions == ["第1步结论", "第2步结论", "第3步结论"]  # 汇总仍全量


def test_fc_mode_prompt_omits_action_options():
    """Function Calling 模式：prompt 不写 JSON 动作格式（schema 走 API 层），
    结论回传改为指向工具的可选参数——两种协议的对照组差异"""
    from game_agent.framework.context import ContextAssembler
    from game_agent.framework.history import HistoryManager
    from game_agent.framework.types import Element, FrameAnalysis

    frame = FrameAnalysis(screenshot=b"\x89PNG",
                          elements=(Element("1", 20, 20),),
                          tags={"1": (20, 20), "2": (60, 20)})
    prompt = ContextAssembler().build(
        Task(goal="g"), frame, HistoryManager().view(), screen_size=(360, 360),
        include_action_options=False)

    assert "# 可翻开的格子" in prompt          # 局面信息保留
    assert "# 行动选项" not in prompt          # JSON 写法由 tools 声明替代
    assert '"type": "click"' not in prompt
    assert "conclusions（字符串数组）" in prompt  # 结论改走工具参数


def test_runner_full_loop_with_scripted_decider():
    """最小闭环验证：capture → prompt → decide → act → check → 循环终止"""
    env = MockEnv(seed=1)
    env.set_target(500, 200)
    received_prompts: list[str] = []

    async def scripted_decider(prompt: str, images: list[bytes]) -> str:
        """模拟一个"完美的多模态LLM"：直接输出命中靶心的动作。
        同时校验管道确实把 prompt 和截图喂了进来。"""
        assert prompt and "任务目标" in prompt
        assert images and images[0][:4] == b"\x89PNG"
        received_prompts.append(prompt)
        return json.dumps({"type": "click", "x": 500, "y": 200})

    runner = AgentRunner(env=env, decider=scripted_decider, step_interval_s=0)
    result = asyncio.run(runner.run(Task(goal="点击白色方块", timeout_steps=10)))

    assert result.status is Status.SUCCESS
    assert result.steps == 1
    assert len(received_prompts) == 1


def test_runner_survives_garbage_then_converges():
    """管道可靠性：LLM 前两次输出垃圾（触发重试反馈环），第三次命中。"""
    env = MockEnv(seed=1)
    env.set_target(500, 200)
    calls = {"n": 0}

    async def flaky_decider(prompt: str, images: list[bytes]) -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            return "我觉得应该点中间附近"                      # 无 JSON → 触发重试
        if calls["n"] == 2:
            return '{"type": "teleport", "x": 1, "y": 1}'      # 非法动作 → 触发重试
        if calls["n"] == 3:
            # 第3次调用 = 第1步内的首次重试，错误反馈必须已注入
            assert "上一次输出无效" in prompt
        # 第2步起为正常调用，prompt 本就不应带反馈
        return json.dumps({"type": "click", "x": 500, "y": 200})

    runner = AgentRunner(env=env, decider=flaky_decider, step_interval_s=0)
    result = asyncio.run(runner.run(Task(goal="点击白色方块", timeout_steps=10)))

    assert result.status is Status.SUCCESS
    assert calls["n"] == 3


def test_runner_fail_on_timeout():
    env = MockEnv(seed=1)
    env.set_target(500, 200)

    async def stubborn_decider(prompt: str, images: list[bytes]) -> str:
        return json.dumps({"type": "click", "x": 10, "y": 10})

    runner = AgentRunner(env=env, decider=stubborn_decider, step_interval_s=0)
    result = asyncio.run(runner.run(Task(goal="点击白色方块", timeout_steps=5)))

    assert result.status is Status.FAIL
    assert result.steps == 5


def test_step_feedback_injected_on_second_step():
    """僵死循环修复：第一步未命中时，第二步 prompt 必须带显式反馈"""
    env = MockEnv(seed=1)
    env.set_target(500, 200)
    prompts: list[str] = []

    async def decider(prompt: str, screenshot: bytes) -> str:
        prompts.append(prompt)
        if len(prompts) == 1:
            return json.dumps({"type": "click", "x": 10, "y": 10})   # 脱靶
        return json.dumps({"type": "click", "x": 500, "y": 200})     # 命中

    runner = AgentRunner(env=env, decider=decider, step_interval_s=0)
    result = asyncio.run(runner.run(Task(goal="点击白色方块", timeout_steps=10)))

    assert result.status is Status.SUCCESS
    assert result.steps == 2
    assert "# 上一步反馈" not in prompts[0]      # 第一步无反馈
    assert "# 上一步反馈" in prompts[1]           # 第二步有反馈
    assert "click(10,10)" in prompts[1]           # 反馈包含上一步动作
    assert "不要原样重复" in prompts[1]
    assert "800×600" in prompts[0]                # 分辨率数字进 prompt
    assert "画面无明显变化特征" in prompts[1]      # 历史摘要补实（非占位）


def test_som_prompt_never_injects_feedback():
    """SoM 三段结构是固定契约：任何反馈都不注入（真实闭环回归锁定）。

    来源切断验证：即使 runner 把 error_feedback/step_feedback 传进
    build（完整模式依赖它），SoM 分支也必须一字不渲染——发给 LLM 的
    信息只含规定内容：固定信息+可翻开格子+行动选项+过往推理结论。
    """
    from game_agent.framework.context import ContextAssembler
    from game_agent.framework.history import HistoryManager
    from game_agent.framework.types import Element, FrameAnalysis

    frame = FrameAnalysis(screenshot=b"\x89PNG",
                          elements=(Element("1", 20, 20),),
                          tags={"1": (20, 20)})
    prompt = ContextAssembler().build(
        Task(goal="g"), frame, HistoryManager().view(), screen_size=(360, 360),
        error_feedback="JSON 解析失败: xxx。原始输出: '{31, 32, 33}'",
        step_feedback="上一步你执行了 [click(1,1)]，动作已执行但任务仍未完成。")

    assert "上一次输出无效" not in prompt   # 解析错误反馈不进 SoM prompt
    assert "JSON 解析失败" not in prompt
    assert "上一步反馈" not in prompt        # 步骤反馈同样不进
    assert "click(1,1)" not in prompt
    assert "# 可翻开的格子" in prompt        # 三段结构本体完整
    assert "# 行动选项" in prompt


def test_stagnation_escalates_feedback():
    """僵滞检测：连续3次相同动作后，反馈升格为强警告（含尝试清单）"""
    env = MockEnv(seed=1)
    env.set_target(500, 200)
    prompts: list[str] = []

    async def fixated_decider(prompt: str, images: list[bytes]) -> str:
        prompts.append(prompt)
        return json.dumps({"type": "click", "x": 10, "y": 10})  # 一直脱靶

    runner = AgentRunner(env=env, decider=fixated_decider, step_interval_s=0)
    result = asyncio.run(runner.run(Task(goal="点击白色方块", timeout_steps=5)))

    assert result.status is Status.FAIL
    assert "上一步反馈" not in prompts[0]                       # 第1步无反馈
    assert "不要原样重复" in prompts[1] and "警告" not in prompts[1]   # 第2步普通反馈
    assert "警告" in prompts[3] and "连续 3 次" in prompts[3]    # 第4步升格
    assert "click(10,10)" in prompts[3]                         # 列出尝试过的动作
    assert "改变行为" in prompts[4]                              # 持续升格


def test_frame_analysis_summary():
    """历史摘要补实：notes 与元素进入单行摘要，不再占位空串"""
    frame = FrameAnalysis(
        screenshot=b"",
        elements=(Element(text="开始游戏", x=100, y=200),
                  Element(text="设置", x=100, y=260)),
    )
    s = frame.summary()
    assert "开始游戏" in s and "(100,200)" in s and "设置" in s
    assert FrameAnalysis(screenshot=b"").summary() == "(画面无明显变化特征)"


def test_mock_env_notes_explain_red_dots():
    """红点说明进 notes：让多模态通道知道红点是自己落的、白块才是目标"""
    env = MockEnv(seed=1)
    env.set_target(500, 200)

    assert env.capture().notes == ""               # 未点击前无说明
    env.act(Action(type="click", x=10, y=10))
    assert "红点" in env.capture().notes           # 点击后出现红点说明
