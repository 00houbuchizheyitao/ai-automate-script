# 扫雷 Agent Benchmark API 文档

> 版本：1.0.0\
> Python：>= 3.10\
> 安装名：`ai-automate-script`\
> 导入名：`game_agent`

本文档面向“把扫雷 Agent Benchmark作为库接入自己的项目”的开发者，内容覆盖公共出口、能力列表与常用指令、构造参数、核心契约、自定义 Environment 模板和 extras 矩阵。

**公共 API 约定**：只把 `game_agent.framework.__all__` 与 `game_agent.llm.__all__` 中的名字视为稳定公共出口；其他模块路径属于高级扩展点，升级时可能变动。

***

## 目录

1. [安装与导入](#1-安装与导入)
2. [公共出口表](#2-公共出口表)
3. [能力列表与常用指令](#3-能力列表与常用指令)
4. [最小可运行示例](#4-最小可运行示例)
5. [核心对象](#5-核心对象)
6. [环境与决策器契约](#6-环境与决策器契约)
7. [自定义 Environment 模板](#7-自定义-environment-模板)
8. [自定义 Decider / LLM 客户端](#8-自定义-decider--llm-客户端)
9. [Extras 矩阵](#9-extras-矩阵)
10. [库使用注意事项](#10-库使用注意事项)
11. [常见错误排查](#11-常见错误排查)

***

## 1. 安装与导入

在仓库根目录安装：

```bash
pip install -e .                    # 核心依赖：httpx + Pillow + python-dotenv
pip install -e ".[benchmark]"       # 无头扫雷跑分
pip install -e ".[window,vision]"   # 真实窗口截屏 + OCR
pip install -e ".[all]"             # 全量
```

在其他项目中安装：

```bash
pip install -e D:\MyCode\ai_automate_script
# 或先构建 wheel，再安装 dist/ 下的 wheel
```

导入：

```python
import game_agent
print(game_agent.__version__)

from game_agent.framework import AgentRunner, Environment, Task
from game_agent.config.settings import AppSettings
from game_agent.llm import create_llm_client
```

注意：**安装名是 `ai-automate-script`，导入名是 `game_agent`**。顶层 `game_agent` 只暴露 `__version__`，实际入口在 `game_agent.framework`、`game_agent.llm` 和 `game_agent.config.settings`。

***

## 2. 公共出口表

### 2.1 `game_agent.framework`

共 20 个公共出口：

| 名称                      | 类别    | 说明                                     |
| ----------------------- | ----- | -------------------------------------- |
| `AgentRunner`           | 循环编排  | 感知 → 组装 → 决策 → 执行 → 判分的主循环             |
| `RunResult`             | 运行结果  | 状态、步数、动作、结论、用量                         |
| `Task`                  | 任务声明  | 目标文本、最大步数、环境自定义参数                      |
| `Status`                | 状态枚举  | `RUNNING` / `SUCCESS` / `FAIL`         |
| `Environment`           | 环境抽象  | `capture` / `act` / `check` / `reset`  |
| `MockEnv`               | 内置环境  | 零 GUI 的合成靶子，适合冒烟测试                     |
| `WindowEnv`             | 内置环境  | 桌面窗口截屏 + 键鼠注入通用层                       |
| `MinesweeperEnv`        | 内置环境  | 真实窗口扫雷                                 |
| `VirtualMinesweeperEnv` | 内置环境  | 无头 SDL 扫雷，可并行跑分                        |
| `Action`                | 动作协议  | 键鼠原语 + SoM 编号 + 推理结论                   |
| `ActionParseError`      | 异常    | 输出无法解析为合法动作                            |
| `parse_action`          | 工具函数  | 从 LLM 原始输出中提取动作                        |
| `ACTION_SCHEMA_HINT`    | 常量    | 动作 JSON 格式提示文本                         |
| `Element`               | 观测    | 感知到的可交互元素                              |
| `FrameAnalysis`         | 观测    | 一帧画面的双通道表示                             |
| `make_llm_decider`      | 适配器   | 把 `BaseLLMClient` 适配成 Runner 的 Decider |
| `RunTraceLogger`        | 观测/复盘 | 每步 prompt、原始输出、截图落盘                    |
| `Perception`            | 感知    | OCR 元素检测，可关闭                           |
| `HistoryManager`        | 记忆    | 滑动窗口历史                                 |
| `HumanDecider`          | 人审    | 人扮演 LLM 的交互式决策器                        |

### 2.2 `game_agent.llm`

共 8 个公共出口：

| 名称                    | 说明                                             |
| --------------------- | ---------------------------------------------- |
| `BaseLLMClient`       | LLM 客户端抽象基类                                    |
| `LLMCapabilities`     | 传输层能力声明：vision / function\_calling / streaming |
| `CapabilityError`     | 客户端缺少调用方要求的能力                                  |
| `ensure_capabilities` | 启动时校验能力                                        |
| `LLMFactoryError`     | provider 配置错误或不支持的选项                           |
| `create_llm_client`   | 按 provider 创建客户端                               |
| `OllamaClient`        | 本地 Ollama 客户端                                  |
| `OnlineLLMClient`     | OpenAI 兼容在线端点客户端                               |

### 2.3 配置

| 名称            | 导入路径                         |
| ------------- | ---------------------------- |
| `AppSettings` | `game_agent.config.settings` |

### 2.4 未列入 `__all__` 的高级扩展点

这些可以导入，但不属于稳定公共 API：

| 名称                         | 导入路径                                          | 用途            |
| -------------------------- | --------------------------------------------- | ------------- |
| `ContextAssembler`         | `game_agent.framework.context`                | 自定义 prompt 组装 |
| `HistoryView` / `Step`     | `game_agent.framework.history`                | 自定义历史视图       |
| `dump_llm_view`            | `game_agent.framework.human_decider`          | 导出“模型将看到的一切”  |
| `Decider`                  | `game_agent.framework.runner` 或 `llm_adapter` | 决策器类型别名       |
| `SomTag` / `draw_som_tags` | `game_agent.framework.som`                    | 自绘 SoM 编号徽章   |

***

## 3. 能力列表与常用指令

> 公共出口表按**代码符号**组织，本节按**用户目的**组织：先在这里找到“我想做成什么事”，再去对应章节查参数。

### 3.1 能力列表

| 我想做的事 | 用哪些对象 / 入口 | 展开看 |
| --- | --- | --- |
| 不调模型，验证感知与管道是否通 | `MockEnv` 或自定义 `Environment` + 任意 async decider | 4.1、6.1 |
| 让视觉模型玩自己的游戏 | 自定义 `Environment`（返回 `tags` 则自动走 SoM）+ `make_llm_decider` | 第 7 节、8.1 |
| 接入真实桌面窗口 | `WindowEnv` 子类 / `MinesweeperEnv`，安装 `[window]` | 5.8、10.5 |
| 无头可复现跑分 | `VirtualMinesweeperEnv` / `MockEnv`，安装 `[benchmark]` | 5.8、第 9 节 |
| 多局并行跑分 | `--env virtual --runs N --parallel M` | 3.2 |
| 对比两种动作协议 | `--fc` 或 `function_calling=True` | 3.2、8.3 |
| 人工审查模型看到的全部信息 | 命令行 `--llm human`（快照）/ 代码 `HumanDecider`（逐回合） | 3.2、5.9 |
| 改 prompt 结构与信息编排 | 替换 `runner.assembler`（`ContextAssembler`） | 3.3 |
| 新增一个模型或后端 | 改 `.env` 端点，或自定义 `BaseLLMClient` | 3.4 |
| 复盘单局每一步 | `RunTraceLogger` | 5.9 |
| 控制历史长度 | `AgentRunner(history_window=...)` / `HistoryManager` | 5.7、5.9 |

### 3.2 常用指令

主入口是 `scripts/run_minesweeper.py`，以下命令均在仓库根目录执行。

**模式对照**

| 模式 | 命令 | 行为 |
| --- | --- | --- |
| 无头（虚拟） | `python scripts/run_minesweeper.py --env virtual --llm online --seed 42` | 游戏在进程内渲染，不占桌面、不动键鼠，可边跑边用电脑 |
| 真实窗口 | 终端 A：`python minesweeper.py 42`<br>终端 B：`python scripts/run_minesweeper.py --env window --llm online` | 截屏 + `pyautogui` 注入真实键鼠；窗口必须可见，运行期间不要动鼠标键盘 |
| 人审快照 | `python scripts/run_minesweeper.py --env window --llm human` | 不调模型，导出“第一帧将发给 LLM 的完整信息”（原图 + SoM 图 + prompt）后结束 |
| 只看感知 | `python scripts/run_minesweeper.py --dry-run` | 只跑 `capture()` + `check()`，不注入任何输入 |
| 完整局 | `python scripts/run_minesweeper.py --env virtual --llm ollama --full-game --fc` | 自动设置 `safe_opens=71`、最大步数 120 |
| 并行跑分 | `python scripts/run_minesweeper.py --env virtual --llm ollama --fc --full-game --runs 20 --parallel 8 --save` | 每局独立 seed / 客户端 / trace；仅支持 `--env virtual` |
| 双协议 A/B | 同一命令加 / 不加 `--fc` | 默认 prompt JSON；`--fc` 走 function calling |

> `--llm human` 是**人审快照**，不是逐回合人扮演。真正的“人代替模型决策”是代码里的 `HumanDecider`（见 5.9），需要在入口脚本里接入，当前命令行没有对应开关：

```python
from game_agent.framework import AgentRunner, HumanDecider

runner = AgentRunner(env=env, decider=HumanDecider(log_path="llm_views/human_view.md"))
```

**参数速查（run_minesweeper.py）**

| 参数 | 取值 | 说明 |
| --- | --- | --- |
| `--env` | `window` / `virtual` | 运行环境；默认 `window` |
| `--llm` | `ollama` / `online` / `human` | 模型后端；默认 `ollama`，`human` 为人审快照 |
| `--model` | 模型名 | 覆盖 `.env` 中的 `OLLAMA_MODEL` / `ONLINE_MODEL` |
| `--seed` | int | virtual 模式起始雷位；并行时逐局 +1 |
| `--safe-opens` | int | 需安全翻开的格子数；默认 3 |
| `--steps` | int | 最大步数；默认 10 |
| `--full-game` | flag | 等价 `safe_opens=71`、`steps=120`，优先于 `--safe-opens` |
| `--fc` | flag | 启用 function calling；不能与 `--llm human` 同用 |
| `--dry-run` | flag | 只感知，不注入键鼠 |
| `--parallel` | int | 并发上限，默认 1；多局仅支持 `--env virtual`，且不支持 `--llm human` / `--dry-run` |
| `--runs` | int | 总局数，默认等于 `--parallel` |
| `--save` | flag | 多局时把汇总归档到 `benchmark_results/` |

**MockEnv 基准入口（run_mock_llm.py）**

| 命令 | 说明 |
| --- | --- |
| `python scripts/run_mock_llm.py --runs 10 --save` | 固定种子出题，统计命中率 / 步数 / 解析错误率 / 耗时 |
| `python scripts/run_mock_llm.py --provider online --model glm-5.3-flash --runs 5` | 指定后端与模型 |

该脚本参数：`--runs`（默认 5）、`--steps`（默认 15）、`--provider`（`ollama` / `online`）、`--model`、`--save`。

**一次性实验脚本**（不属于稳定入口，参数与结论仅供选型参考）

| 命令 | 用途 |
| --- | --- |
| `python scripts/ocr_scale_experiment.py 123` | 测相邻数字在不同放大倍数下的 OCR 识别率 |
| `python scripts/max_tokens_experiment.py` | 测 `max_tokens` 预算对“始终思考”模型响应的影响 |

### 3.3 自定义上下文

`ContextAssembler` 决定每一步发给 LLM 的 prompt 长什么样：把 `Task`、`FrameAnalysis`、历史、结论、错误反馈拼成最终文本。它不在稳定公共出口里，属于高级扩展点：

```python
from game_agent.framework.context import ContextAssembler
```

`AgentRunner` 构造时固定写入 `self.assembler = ContextAssembler()`，没有构造参数。替换方式是构造后赋值（或继承 `AgentRunner`）：

```python
from game_agent.framework import AgentRunner
from game_agent.framework.context import ContextAssembler


class MyAssembler(ContextAssembler):
    def build(self, task, frame, history, screen_size=None,
              error_feedback=None, step_feedback=None,
              conclusions=None, include_action_options=True) -> str:
        parts = [f"# 目标\n{task.goal}", f"# 当前画面\n{frame.describe()}"]
        if conclusions:
            parts.append("# 上一步结论\n" + "\n".join(conclusions))
        if error_feedback:
            parts.append(f"# 上次输出无效，请修正\n{error_feedback}")
        return "\n\n".join(parts)


runner = AgentRunner(env=env, decider=decider)
runner.assembler = MyAssembler()
```

两套内置模板的分支条件：

- `frame.tags` 非空 → **SoM 极简模式**：固定说明 + 行动选项 + 上一步结论三段式，不消费历史与错误反馈（解析重试等于原样重发）。
- `frame.tags` 为空 → **完整模式**：目标 + 动作 schema + 屏幕尺寸 + 历史 + 上一步反馈 + 错误反馈 + 当前画面元素。

自定义时注意：`error_feedback` 只在解析失败重试时传入；丢掉了它，模型就看不到“上次为什么错”。

### 3.4 新增模型与模型切换

**切换已有模型**（优先级：代码显式参数 > 命令行 > `.env`）

| 场景 | 做法 |
| --- | --- |
| 临时切后端 | `--llm ollama` / `--llm online` |
| 临时切模型 | `--model <模型名>` |
| 改默认后端 | `.env` 的 `LLM_PROVIDER=ollama` / `online` |
| 改默认模型 | `.env` 的 `OLLAMA_MODEL` / `ONLINE_MODEL` |
| 代码里指定 | `create_llm_client(settings, provider=..., model=...)` |

在线端点的三件套是 `ONLINE_BASE_URL`、`ONLINE_API_KEY`、`ONLINE_MODEL`。非智谱兼容端点通常还需要把 `ONLINE_THINKING` 设为 `default`（不发送 `thinking` 字段）。

**新增模型**

1. **OpenAI 兼容端点**（DeepSeek / Qwen / vLLM / 自建网关）：不改代码。填好 `.env` 的 `ONLINE_BASE_URL`、`ONLINE_API_KEY`、`ONLINE_MODEL`，然后 `--llm online --model <模型名>`。
2. **本地 Ollama**：先 `ollama pull <模型名>`，再 `--llm ollama --model <模型名>`，或改 `OLLAMA_MODEL`。用 `ollama show <模型名>` 确认具备 `vision`；要用 `--fc` 还需要 `tools`。
3. **非 OpenAI 协议**：继承 `BaseLLMClient` 实现 `capabilities`、`generate`、`generate_with_images`、`stream_generate`，然后绕过工厂直接接入：

```python
from game_agent.framework import AgentRunner, make_llm_decider
from game_agent.llm import ensure_capabilities

client = MyClient(...)
ensure_capabilities(client, vision=True, function_calling=False)
runner = AgentRunner(env=env, decider=make_llm_decider(client))
```

工厂目前只支持 `ollama` 和 `online`（`openai`、`openai-compatible` 是 `online` 的别名），**没有 provider 注册钩子**。要让 `create_llm_client(provider="myprovider")` 生效，需要修改 `game_agent/llm/factory.py` 的分支与别名表。

**硬性要求**：Runner 每步发送原图 + SoM 图，模型必须支持图像输入；`--fc` 还要求端点与模型支持 tools。工厂只校验客户端声明的传输层能力，不探测具体模型。

***

## 4. 最小可运行示例

### 4.1 不调用模型：验证管道

`MockEnv` 是一个 800×600 的合成游戏，画面中央有一个白色方块，点击命中即成功。下面用固定靶心坐标的假决策器跑通闭环：

```python
import asyncio

from game_agent.framework import AgentRunner, MockEnv, Task


async def main() -> None:
    env = MockEnv(seed=1)

    async def decider(prompt: str, images: list[bytes]) -> str:
        # 演示用：直接点击靶心。
        # 真实接入见 4.2，把这里换成 make_llm_decider(client)。
        x, y = env.target
        return f'{{"type": "click", "x": {x}, "y": {y}}}'

    runner = AgentRunner(env=env, decider=decider)
    result = await runner.run(Task(goal="点击画面中的白色方块", timeout_steps=5))
    print(result.status.value, result.steps, result.actions)


if __name__ == "__main__":
    asyncio.run(main())
```

### 4.2 接入真实 LLM

```python
import asyncio

from game_agent.config.settings import AppSettings
from game_agent.framework import (
    AgentRunner,
    MockEnv,
    RunTraceLogger,
    Task,
    make_llm_decider,
)
from game_agent.llm import create_llm_client


async def main() -> None:
    settings = AppSettings()
    client = create_llm_client(
        settings,
        provider="ollama",
        model="mimo-v2.6:9b",
    )
    runner = AgentRunner(
        env=MockEnv(seed=1),
        decider=make_llm_decider(client),
        parse_retries=2,
        trace_logger=RunTraceLogger("llm_views/api_demo/run_trace.md"),
    )
    result = await runner.run(Task(goal="点击画面中的白色方块", timeout_steps=10))
    print(result.status.value, result.steps, len(result.actions))
    print(result.usage)


if __name__ == "__main__":
    asyncio.run(main())
```

运行后查看：

```text
llm_views/api_demo/run_trace.md
llm_views/api_demo/trace_step*_try*_img*.png
```

***

## 5. 核心对象

### 5.1 `Task`

```python
Task(
    goal: str,
    timeout_steps: int = 30,
    meta: dict = {},
)
```

| 字段              | 类型     | 说明                                                 |
| --------------- | ------ | -------------------------------------------------- |
| `goal`          | `str`  | 每步常驻的任务目标文本                                        |
| `timeout_steps` | `int`  | 最大步数；用完仍未达标则由 Runner 判定 `FAIL`                     |
| `meta`          | `dict` | 传给 `Environment.check()` 的自定义参数，例如扫雷的 `safe_opens` |

示例：

```python
task = Task(
    goal="这是扫雷游戏，请安全翻开格子。",
    timeout_steps=120,
    meta={"safe_opens": 71},
)
```

### 5.2 `Status`

```python
class Status(Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAIL = "fail"
```

`Environment.check()` 每一步返回一个 `Status`；只要不是 `RUNNING`，Runner 就结束本局。

### 5.3 `Action`

```python
Action(
    type: str,                 # key / click / flag / move / wait
    key: str | None = None,
    x: int | None = None,
    y: int | None = None,
    ms: int = 50,
    id: str | None = None,     # SoM 编号（单个）
    ids: tuple[str, ...] = (), # SoM 编号（多个）
    conclusions: tuple[str, ...] = (),
)
```

| 字段            | 说明                                                  |
| ------------- | --------------------------------------------------- |
| `type`        | 动作类型，必须是 `key` / `click` / `flag` / `move` / `wait` |
| `key`         | `key` 动作的按键名，如 `"w"`、`"space"`                      |
| `x` / `y`     | 图像坐标系下的坐标；Runner 会把编号解析成坐标                          |
| `ms`          | `wait` 的毫秒数，或动作附带时长                                 |
| `id` / `ids`  | SoM 编号；Runner 在当前帧的 `frame.tags` 中查坐标               |
| `conclusions` | 本步推理结论，会进入整局结论记忆，并注入下一步 prompt                      |

`Action.validate()` 会校验类型与参数；`Action.describe()` 返回人类可读描述，例如 `click(ids:31,32)`。

### 5.4 `FrameAnalysis`

```python
FrameAnalysis(
    screenshot: bytes,
    elements: tuple[Element, ...] = (),
    notes: str = "",
    annotated: bytes | None = None,
    tags: dict[str, tuple[int, int]] | None = None,
    opened_ids: frozenset[str] | None = None,
)
```

| 字段           | 说明                                           |
| ------------ | -------------------------------------------- |
| `screenshot` | 原始画面 PNG 字节；作为发给 LLM 的第一张图                   |
| `elements`   | OCR/感知得到的结构化元素                               |
| `notes`      | 画面语义说明，会进入 prompt 的结构化通道                     |
| `annotated`  | 附加图，例如 SoM 编号标注图；作为第二张图发送                    |
| `tags`       | SoM 编号 → 图像坐标；存在时 Runner 会解析 `Action.id/ids` |
| `opened_ids` | 已翻开/已完成目标的编号集合；当前 Runner 不消费，供环境或外部分析使用      |

方法：

- `describe()`：结构化通道的文本表示，包含 `notes` 和元素列表。
- `summary()`：单行摘要，供历史记录压缩使用。

### 5.5 `Element`

```python
Element(
    text: str,
    x: int,
    y: int,
    confidence: float = 1.0,
)
```

感知层检测到的可交互目标。`x` / `y` 是图像坐标。

### 5.6 `RunResult`

```python
@dataclass
class RunResult:
    status: Status
    steps: int
    actions: list[Action]
    conclusions: list[str]
    usage: dict
```

| 字段            | 说明                                          |
| ------------- | ------------------------------------------- |
| `status`      | `SUCCESS` 或 `FAIL`；解析重试耗尽会抛异常，不返回 RunResult |
| `steps`       | 结束时的步数；步数耗尽时等于 `timeout_steps`              |
| `actions`     | 整局执行过的所有子动作（一次多格决策会产生多个）                    |
| `conclusions` | 整局累积的推理结论                                   |
| `usage`       | token/耗时汇总，见下表                              |

`usage` 的键：

| 键                                             | 说明                           |
| --------------------------------------------- | ---------------------------- |
| `prompt_tokens` / `completion_tokens`         | 累计 token                     |
| `prompt_eval_ms` / `eval_ms` / `total_ms`     | 模型耗时（Ollama 提供）              |
| `calls`                                       | LLM 调用次数，包含解析重试              |
| `max_seq`                                     | 单次调用最大 `prompt + completion` |
| `max_prompt_tokens` / `max_completion_tokens` | 单次调用峰值                       |
| `length_stops`                                | `done_reason=length` 的次数     |

> 当前在线客户端 `OnlineLLMClient` 不采集 token usage；使用它时 `usage` 中 token 相关字段为 0。`done_reason` 只在单步 trace 中记录，不在 `RunResult.usage` 汇总。

### 5.7 `AgentRunner`

```python
AgentRunner(
    env: Environment,
    decider: Decider,
    history_window: int = 5,
    parse_retries: int = 2,
    step_interval_s: float = 0.2,
    stagnation_feedback_at: int = 3,
    trace_logger: RunTraceLogger | None = None,
    on_step: Callable[[int, list[Action], Status], None] | None = None,
    include_action_options: bool = True,
)
```

| 参数                       | 说明                                                               |
| ------------------------ | ---------------------------------------------------------------- |
| `env`                    | 环境实例                                                             |
| `decider`                | `async (prompt, images) -> str`；可用 `make_llm_decider` 包装 LLM 客户端 |
| `history_window`         | 历史窗口步数；更早的步骤压成一行摘要                                               |
| `parse_retries`          | 解析失败后的额外重试次数；总尝试次数 = `1 + parse_retries`                         |
| `step_interval_s`        | 同一决策内多个子动作之间的等待秒数                                                |
| `stagnation_feedback_at` | 连续多少个完全相同的非 wait 动作后注入僵滞警告                                       |
| `trace_logger`           | 每步追踪日志；`None` 表示不记录                                              |
| `on_step`                | 每步结束回调 `on_step(step, subs, status)`；回调异常会被吞掉                    |
| `include_action_options` | 是否在 prompt 中写动作 JSON 格式；Function Calling 模式设为 `False`            |

`run(task) -> RunResult` 的行为：

1. 调用 `env.reset()`，清空历史与用量。
2. 每步：`env.capture()` → `ContextAssembler.build()` → `decider()` → 解析 → `env.act()` → `env.check()`。
3. 一次决策可返回多个动作（`ids` 数组），Runner 逐个执行并记录。
4. `check()` 返回非 `RUNNING` 时结束并返回 `RunResult`。
5. 步数耗尽返回 `FAIL`；解析重试耗尽抛出 `ActionParseError`；其他异常原样抛出。
6. `trace_logger.log_finish()` 在 `finally` 中调用，异常中断也会留档。

行为细节：

- **解析重试**：完整模式下会把错误信息回喂并重建 prompt；SoM 模式下 `ContextAssembler` 不消费错误反馈，重试是原样重发。
- **僵滞检测**：只对非 `wait` 动作计数；SoM 模式下 `step_feedback` 不注入，因此该警告主要作用于完整模式。
- **结论记忆**：整局所有结论累积到 `RunResult.conclusions`，但下一步 prompt 只注入上一步的结论。
- **坐标裁剪**：`parse_action` 会按 `screen_size` 把 `x/y` 限制在画面范围内。

### 5.8 内置环境

#### `MockEnv`

```python
MockEnv(seed: int | None = 42)
```

| 参数     | 说明                        |
| ------ | ------------------------- |
| `seed` | 固定靶位种子；`reset()` 会恢复到同一靶位 |

- 800×600 合成画面，白色方块是目标；点击命中半径 `HIT_HALF=34`。
- 只依赖核心依赖（Pillow），不碰桌面，适合 CI 和冒烟测试。
- `set_target(x, y)` 是测试钩子，可固定靶位跨 `reset()` 存活。

#### `WindowEnv`

```python
WindowEnv(
    region: tuple[int, int, int, int] | None = None,
    window_title: str | None = None,
    use_ocr: bool = True,
    ocr_languages: list[str] | None = None,
    act_interval_s: float = 0.1,
    dry_run: bool = False,
    content_threshold: float = 0.5,
    auto_activate: bool = True,
    resolve_timeout_s: float = 10.0,
    resolve_interval_s: float = 1.0,
)
```

| 参数                   | 说明                                                               |
| -------------------- | ---------------------------------------------------------------- |
| `region`             | 截屏区域 `(left, top, width, height)`；与 `window_title` 二选一，都为空时用主显示器 |
| `window_title`       | 窗口标题子串；每次 `capture()` 重新定位并跟随窗口移动                                |
| `use_ocr`            | 是否跑 OCR 感知；纯图形游戏可关闭以省时                                           |
| `ocr_languages`      | OCR 语言列表，默认 `["ch_sim", "en"]`                                   |
| `act_interval_s`     | 每个动作后的统一等待秒数                                                     |
| `dry_run`            | 只记录坐标翻译，不注入真实键鼠                                                  |
| `content_threshold`  | 子类提供 `_content_score()` 时的内容匹配阈值                                 |
| `auto_activate`      | 定位候选窗口时是否尝试带到前台                                                  |
| `resolve_timeout_s`  | 窗口定位/内容校验的总重试时限                                                  |
| `resolve_interval_s` | 重试间隔                                                             |

说明：

- `WindowEnv` 仍是抽象类，子类必须实现 `check()`。
- `capture()` 使用 `Perception` 做 OCR；`act()` 把图像坐标平移为屏幕绝对坐标后调用 `pyautogui`。
- 子类可覆盖 `_content_score(png) -> float | None` 区分标题相同的干扰窗口；返回 `None` 表示不校验。
- 真实窗口依赖 `[window]` extras；OCR 依赖 `[vision]` extras。

#### `MinesweeperEnv`

```python
MinesweeperEnv(
    window_title: str = "扫雷",
    settle_s: float = 0.35,
    board_origin: tuple[int, int] | None = None,
    **kwargs,  # 透传给 WindowEnv
)
```

| 参数             | 说明                               |
| -------------- | -------------------------------- |
| `window_title` | 游戏窗口标题子串                         |
| `settle_s`     | 动作后等待游戏渲染的秒数                     |
| `board_origin` | 棋盘在截图中的偏移；默认 `(8, 31)`，分类错位时用于校正 |

- 棋盘为 360×360（9×9、每格 40px）。
- `Task.meta["safe_opens"]` 控制需要翻开的安全格数，默认 3。
- `check()` 通过 OCR 识别 `WIN`/`LOSE`，无结算画面时统计数字格。
- `reset()` 发送 `R` 键重开；`act()` 在结算后不再注入动作，避免“点击重开”。
- `click_cell(col, row)` 是无头/调试用的便捷点击方法。
- 通过 `_content_score()` 的颜色签名区分标题含“扫雷”的其他窗口。

#### `VirtualMinesweeperEnv`

```python
VirtualMinesweeperEnv(
    seed: int | None = 42,
    use_ocr: bool = True,
    settle_s: float = 0.0,
)
```

| 参数         | 说明                    |
| ---------- | --------------------- |
| `seed`     | 雷位种子；`reset()` 会重建同一局 |
| `use_ocr`  | 是否对渲染画面跑 OCR          |
| `settle_s` | 动作后等待渲染的秒数；无头环境通常为 0  |

- 使用 SDL dummy 渲染 + 进程内事件注入；不需要桌面、不碰鼠标键盘。
- 支持多实例并行，适合 benchmark。
- 游戏逻辑与仓库根目录的 `minesweeper.py` 相同；Agent 依然只看渲染像素。
- 需要 `[minesweeper]` 或 `[benchmark]` extras（`pygame`）。
- `flag` 动作只更新视觉标记，不改变游戏内旗子状态。

### 5.9 观测与工具

#### `RunTraceLogger`

```python
RunTraceLogger(log_path: str | Path = "llm_views/run_trace/run_trace.md")
```

- 初始化时清空旧日志和同名截图目录。
- `log_step(...)` 记录一次 LLM 调用（含重试），返回落盘图片路径。
- `log_finish(...)` 记录结束原因、总步数、动作序列、用量汇总。
- 通常由 `AgentRunner(trace_logger=...)` 自动调用，不需要手动写。

```python
log_step(
    step: int,
    prompt: str,
    images: list[bytes],
    raw_output: str,
    parsed: list[str] | None,
    status: str,
    conclusions: list[str],
    elapsed_s: float | None = None,
    usage: dict | None = None,
    thinking: str = "",
) -> list[str]

log_finish(
    reason: str,
    steps: int,
    max_steps: int,
    actions: list[Action],
    conclusions: list[str],
    usage: dict | None = None,
) -> None
```

#### `Perception`

```python
Perception(use_ocr: bool = True, ocr_languages: list[str] | None = None)
```

```python
analyze(screenshot: bytes, ocr_enabled: bool | None = None) -> FrameAnalysis
```

- OCR 惰性加载：优先 RapidOCR，不可用时回退 easyocr。
- OCR 异常不会打断循环，会降级为带 `notes` 的纯图像 `FrameAnalysis`。
- 不需要 OCR 时传 `use_ocr=False`，可避免安装 `[vision]`。

#### `HistoryManager`

```python
HistoryManager(window: int = 5)
```

| 方法                                                      | 说明                        |
| ------------------------------------------------------- | ------------------------- |
| `record(step_index, analysis_summary, actions, status)` | 追加一步记录                    |
| `view() -> HistoryView`                                 | 最近 `window` 步全量，更早的压成一行摘要 |
| `clear()`                                               | 清空历史                      |

通常由 `AgentRunner` 内部使用；需要替换记忆策略时，可自定义该类。

#### `HumanDecider`

```python
HumanDecider(
    log_path: str | Path = "llm_view.md",
    normalizer: Callable[[bytes], bytes] | None = None,
    ask: Callable[[str], str] = input,
)
```

- `async __call__(prompt, images) -> str`，满足 Decider 协议。
- 每次调用把图片和 prompt 落盘，然后在终端询问用户输入 JSON 动作。
- `normalizer` 可传入与在线客户端相同的图像重编码函数，保证人看到的 = LLM 看到的。
- 适合人工审查感知质量和 prompt，不适合无人值守运行。

```python
dump_llm_view(
    env,
    task: Task,
    out_dir: str | Path = "llm_views",
    normalizer: Callable[[bytes], bytes] | None = None,
) -> Path
```

只导出“第一步将发给 LLM 的完整信息”，不调用模型。

#### `make_llm_decider`

```python
make_llm_decider(client: BaseLLMClient) -> Decider
```

- 返回一个 async 可调用对象，内部调用 `client.generate_with_images()`。
- 每次调用后从客户端读取 `last_usage` 和 `last_thinking`，供 Runner 汇总。
- 客户端不支持时，这两个属性为 `None` / 空串。

### 5.10 `BaseLLMClient` 接口

```python
class BaseLLMClient(ABC):
    @property
    @abstractmethod
    def capabilities(self) -> LLMCapabilities: ...

    @abstractmethod
    async def generate(self, prompt: str, history: list[dict] | None = None) -> str: ...

    @abstractmethod
    async def generate_with_images(
        self, prompt: str, images: list[bytes],
        history: list[dict] | None = None,
    ) -> str: ...

    async def generate_with_image(
        self, prompt: str, image_bytes: bytes,
        history: list[dict] | None = None,
    ) -> str: ...

    @abstractmethod
    async def stream_generate(self, prompt: str, history: list[dict] | None = None): ...
```

| 方法                     | 说明                                        |
| ---------------------- | ----------------------------------------- |
| `capabilities`         | 声明 vision / function\_calling / streaming |
| `generate`             | 纯文本生成                                     |
| `generate_with_images` | 多图生成；Runner 实际使用的入口                       |
| `generate_with_image`  | 单图便捷方法，基类默认委托给多图版本                        |
| `stream_generate`      | 异步生成器；不同客户端实现程度不同                         |

### 5.11 `AppSettings` 关键配置

`AppSettings` 是类属性式配置，模块导入时读取环境变量并执行 `load_dotenv()`；`AppSettings()` 构造时创建输出目录。

| 变量                      | 默认值                      | 说明                                                |
| ----------------------- | ------------------------ | ------------------------------------------------- |
| `LLM_PROVIDER`          | `ollama`                 | 默认后端：`ollama` / `online`                          |
| `OLLAMA_BASE_URL`       | `http://localhost:11434` | 本地端点                                              |
| `OLLAMA_MODEL`          | `mimo-v2.6:9b`           | 本地模型                                              |
| `OLLAMA_NUM_CTX`        | `16384`                  | 上下文长度                                             |
| `OLLAMA_TEMPERATURE`    | `0.2`                    | 采样温度                                              |
| `OLLAMA_TOP_P`          | `0.9`                    | nucleus sampling                                  |
| `OLLAMA_NUM_PREDICT`    | `4096`                   | 单次输出上限                                            |
| `OLLAMA_THINK`          | `false`                  | `default` 不传；`true/false` 显式开关                    |
| `OLLAMA_TIMEOUT`        | `300`                    | 请求超时秒数                                            |
| `ONLINE_BASE_URL`       | 智谱开放平台                   | OpenAI 兼容端点                                       |
| `ONLINE_API_KEY`        | 空                        | 在线模型密钥                                            |
| `ONLINE_MODEL`          | `glm-5.3-flash`          | 在线模型                                              |
| `ONLINE_TIMEOUT`        | `60`                     | 流式读超时（两次字节间隔）                                     |
| `ONLINE_THINKING`       | `off`                    | `off` / `on` / `low` / `high` / `max` / `default` |
| `ONLINE_MAX_TOKENS`     | `0`                      | 0 = 不传字段                                          |
| `OCR_LANGUAGES`         | `ch_sim,en`              | OCR 语言                                            |
| `OCR_USE_GPU`           | `false`                  | OCR 是否用 GPU                                       |
| `SCRIPTS_OUTPUT_DIR`    | `<cwd>/output`           | 脚本输出目录（默认导入时 cwd，不自动创建）                             |
| `SCRIPT_PAUSE_INTERVAL` | `0.5`                    | 脚本暂停间隔                                            |
| `LOG_LEVEL`             | `INFO`                   | 日志级别                                              |

> `SCRIPTS_OUTPUT_DIR` 默认是导入时工作目录下的 `output/`，不基于 `settings.py` 的位置计算，也不会在 `AppSettings()` 构造时自动创建；需要写入时由调用方自行 `mkdir`。

***

## 6. 环境与决策器契约

### 6.1 `Environment`

```python
class Environment(ABC):
    @property
    @abstractmethod
    def screen_size(self) -> tuple[int, int]: ...

    @abstractmethod
    def capture(self) -> FrameAnalysis: ...

    @abstractmethod
    def act(self, action: Action) -> None: ...

    @abstractmethod
    def check(self, task: Task) -> Status: ...

    def reset(self) -> None: ...
```

| 方法            | 调用时机       | 要求                                         |
| ------------- | ---------- | ------------------------------------------ |
| `screen_size` | 解析动作、裁剪坐标时 | 返回 `(width, height)`，与 `capture()` 图像尺寸一致  |
| `capture`     | 每步决策前      | 返回 `FrameAnalysis`，`screenshot` 必须是 PNG 字节 |
| `act`         | 每步解析后      | 同步执行；内部自行处理节流/渲染等待；收到的坐标已经解析为图像坐标          |
| `check`       | 每步执行后      | 返回 `RUNNING` / `SUCCESS` / `FAIL`；应尽量轻量    |
| `reset`       | 每局开始时      | 默认无操作；跑分/重复运行必须实现                          |

**SoM 约定**：

- 如果 `capture()` 返回非空 `tags`，Runner 会把 `Action.id/ids` 解析成 `tags` 中的坐标。
- 如果返回 `annotated`，它作为第二张图发给 LLM。
- 引用不存在的编号会抛 `ActionParseError`，触发重试。
- 当前 SoM 极简 prompt 模板是扫雷语义（“可翻开的格子 / 标记雷格”）。非扫雷游戏建议先不设置 `tags`，用原始 x/y 坐标；或者自定义 `ContextAssembler`。

### 6.2 `Decider`

```python
Decider = Callable[[str, list[bytes]], Awaitable[str]]
```

```python
async def decide(prompt: str, images: list[bytes]) -> str:
    ...
```

| 参数           | 说明                                 |
| ------------ | ---------------------------------- |
| `prompt`     | `ContextAssembler` 组装的完整文本         |
| `images[0]`  | 原始截图                               |
| `images[1:]` | 附加图，例如 SoM 标注图                     |
| 返回值          | 包含动作 JSON 的文本；解析器会宽容提取，不要求只输出 JSON |

可选属性（供 Runner 采集指标）：

- `decider.last_usage`：最近一次调用的 usage 字典。
- `decider.last_thinking`：最近一次调用的思考过程。

`make_llm_decider(client)` 会自动从客户端读取这两个属性。

### 6.3 动作解析

```python
parse_action(raw: str, screen_size: tuple[int, int] | None = None) -> Action
```

- 从原始输出中枚举所有平衡的 `{...}` 片段，取最后一个 `type` 在动作词汇表内的 JSON 对象。
- 支持推理正文里出现 `{1, 10}` 这类非 JSON 集合记号。
- 同时收集 `conclusions`：随动作对象、独立 JSON 对象、裸键值、标题后裸数组都可以。
- `id/ids` 的坐标解析不在这一步，由 Runner 用当前帧的 `tags` 完成。
- 失败抛 `ActionParseError`，错误信息会用于重试。

***

## 7. 自定义 Environment 模板

下面是一个完整可运行的最小环境：画面中央有一个白色方块，点击命中即通关。它使用原始 x/y 坐标，不启用 SoM，因此走通用完整 prompt。

```python
from __future__ import annotations

import asyncio
import io

from PIL import Image, ImageDraw

from game_agent.config.settings import AppSettings
from game_agent.framework import (
    Action,
    AgentRunner,
    Environment,
    FrameAnalysis,
    Status,
    Task,
    make_llm_decider,
)
from game_agent.llm import create_llm_client


class ClickTargetEnv(Environment):
    """点击画面中央的白色方块即可通关。"""

    WIDTH, HEIGHT = 320, 240
    TARGET = (160, 120)
    HALF = 20

    def __init__(self) -> None:
        self.hit = False

    @property
    def screen_size(self) -> tuple[int, int]:
        return (self.WIDTH, self.HEIGHT)

    def capture(self) -> FrameAnalysis:
        img = Image.new("RGB", (self.WIDTH, self.HEIGHT), (32, 32, 38))
        draw = ImageDraw.Draw(img)
        cx, cy = self.TARGET
        draw.rectangle(
            [cx - self.HALF, cy - self.HALF, cx + self.HALF, cy + self.HALF],
            fill=(245, 245, 245),
        )
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return FrameAnalysis(
            screenshot=buf.getvalue(),
            notes="画面中央的白色方块是目标；点击它即可通关。",
        )

    def act(self, action: Action) -> None:
        if action.type == "click" and action.x is not None and action.y is not None:
            cx, cy = self.TARGET
            self.hit = (
                abs(action.x - cx) <= self.HALF
                and abs(action.y - cy) <= self.HALF
            )

    def check(self, task: Task) -> Status:
        return Status.SUCCESS if self.hit else Status.RUNNING

    def reset(self) -> None:
        self.hit = False


async def main() -> None:
    settings = AppSettings()
    client = create_llm_client(
        settings,
        provider="ollama",
        model="mimo-v2.6:9b",
    )
    runner = AgentRunner(
        env=ClickTargetEnv(),
        decider=make_llm_decider(client),
        parse_retries=2,
    )
    result = await runner.run(
        Task(goal="点击画面中央的白色方块", timeout_steps=10)
    )
    print(result.status.value, result.steps, result.actions)


if __name__ == "__main__":
    asyncio.run(main())
```

### 7.1 模板要点

- `screen_size` 必须与 `capture()` 生成的图像尺寸一致，否则坐标裁剪会错位。
- `capture()` 返回的 `screenshot` 必须是 PNG 字节；可以用 PIL 生成。
- `act()` 收到的 `action.x/y` 已经是图像坐标；如果环境需要屏幕绝对坐标，自行加偏移。
- `check()` 每步都会调用，避免在里面做重活；需要截图时尽量复用 `capture()` 的结果。
- `reset()` 在每局开始时调用；跑分场景必须实现。
- 需要结构化感知时，在 `capture()` 中设置 `elements` 和 `notes`；需要 SoM 时再设置 `tags`/`annotated`。

### 7.2 启用 SoM 编号

如果要让模型报编号而不是坐标，`capture()` 返回：

```python
return FrameAnalysis(
    screenshot=png,
    annotated=annotated_png,       # 第二张图：编号徽章
    tags={"1": (x1, y1), "2": (x2, y2)},
    notes="编号在目标中心；引用编号即可点击。",
)
```

Runner 会自动把 `{"type": "click", "id": "1"}` 解析成坐标。注意当前 SoM 极简 prompt 模板面向扫雷语义；非扫雷游戏要么使用原始 x/y，要么自定义 `ContextAssembler`。

***

## 8. 自定义 Decider / LLM 客户端

### 8.1 直接写一个 Decider

不继承任何客户端，直接实现一个 async 函数即可：

```python
async def my_decider(prompt: str, images: list[bytes]) -> str:
    # prompt: 完整文本
    # images[0]: 原始截图；images[1:]: 附加图（如 SoM 标注图）
    return '{"type": "click", "x": 160, "y": 120}'


runner = AgentRunner(env=my_env, decider=my_decider)
```

适合接入任意 HTTP API、本地脚本或规则策略。

### 8.2 继承 `BaseLLMClient`

```python
from game_agent.llm import BaseLLMClient, LLMCapabilities


class MyClient(BaseLLMClient):
    @property
    def capabilities(self) -> LLMCapabilities:
        return LLMCapabilities(vision=True, function_calling=False, streaming=False)

    async def generate(self, prompt: str, history=None) -> str:
        ...

    async def generate_with_images(self, prompt: str, images: list[bytes],
                                   history=None) -> str:
        # Runner 通过 make_llm_decider 实际只调用这个方法
        ...

    async def stream_generate(self, prompt: str, history=None):
        yield await self.generate(prompt, history)
```

要点：

- `AgentRunner` 只依赖 `generate_with_images`；其余方法是接口完整性。
- `generate_with_image` 在基类中有默认实现，会委托给 `generate_with_images`。
- 如果想上报用量，在每次调用后设置 `self.last_usage`：
  ```python
  self.last_usage = {
      "prompt_tokens": 100,
      "completion_tokens": 20,
      "prompt_eval_ms": 0.0,
      "eval_ms": 0.0,
      "total_ms": 0.0,
      "done_reason": "stop",
  }
  ```
- 如果有思考过程，设置 `self.last_thinking`。

### 8.3 使用内置客户端

```python
from game_agent.config.settings import AppSettings
from game_agent.llm import create_llm_client

settings = AppSettings()
client = create_llm_client(
    settings,
    provider="online",          # online / ollama / openai / openai-compatible
    model="glm-5.3-flash",
    function_calling=False,
)
```

在线 provider 需要在 `.env` 或环境变量中配置 `ONLINE_API_KEY`。

`create_llm_client` 签名：

```python
create_llm_client(
    settings: AppSettings,
    provider: str | None = None,
    model: str | None = None,
    *,
    function_calling: bool = False,
    progress_callback: Callable[[int], None] | None = None,
) -> BaseLLMClient
```

- `provider` 为空时读 `settings.LLM_PROVIDER`。
- `provider="openai"` / `"openai-compatible"` 都映射到 `online`。
- `progress_callback` 只支持 online；Ollama 传入会抛 `LLMFactoryError`。
- 创建后会调用 `ensure_capabilities(..., vision=True, function_calling=...)`。

### 8.4 `OnlineLLMClient`

```python
OnlineLLMClient(
    api_key: str,
    model: str,
    base_url: str | None = None,
    timeout: int = 120,
    thinking: str = "off",
    max_tokens: int | None = None,
    function_calling: bool = False,
    progress_callback: Callable[[int], None] | None = None,
    progress_interval_s: float = 30.0,
)
```

| 参数                  | 说明                                                |
| ------------------- | ------------------------------------------------- |
| `base_url`          | OpenAI 兼容端点，默认智谱开放平台                              |
| `timeout`           | 流式读超时：两次字节之间的最大间隔，不是总时长                           |
| `thinking`          | `off` / `on` / `low` / `high` / `max` / `default` |
| `max_tokens`        | `None`/`0` 表示不传该字段；正值是生成硬顶                        |
| `function_calling`  | 是否在请求中发送 `tools`                                  |
| `progress_callback` | 每隔 `progress_interval_s` 秒收到“已接收字符数”              |

当前限制：不采集 token usage，`last_usage` 不存在；`reasoning_content` 只用于进度显示，不写入 `last_thinking`。

### 8.5 `OllamaClient`

```python
OllamaClient(
    settings: AppSettings,
    function_calling: bool = False,
    num_ctx: int | None = None,
    temperature: float | None = None,
    top_p: float | None = None,
    num_predict: int | None = None,
    think: bool | None = None,
)
```

- 未传参数时读取 `AppSettings` 的 `OLLAMA_*` 默认值。
- `think=None` 表示不发送 `think` 字段；`True/False` 显式开关。
- `last_usage` 会包含 `prompt_tokens`、`completion_tokens`、`prompt_eval_ms`、`eval_ms`、`total_ms`、`done_reason`。
- `last_thinking` 会保存模型返回的 `thinking` 内容。
- `stream_generate` 是真正的流式生成器；`generate_with_images` 是非流式。

### 8.6 `LLMCapabilities` 与 `ensure_capabilities`

```python
LLMCapabilities(
    vision: bool = False,
    function_calling: bool = False,
    streaming: bool = False,
)
```

```python
ensure_capabilities(
    client: BaseLLMClient,
    *,
    vision: bool = False,
    function_calling: bool = False,
) -> None
```

缺少能力时抛 `CapabilityError`。注意：能力声明是**传输层**的，不代表某个具体模型一定支持视觉或 tools；模型能力由调用方保证。

***

## 9. Extras 矩阵

| extras           | 安装内容                                                    | 适用场景                             |
| ---------------- | ------------------------------------------------------- | -------------------------------- |
| 无（核心）            | `httpx`、`Pillow`、`python-dotenv`                        | `MockEnv`、LLM 客户端、Runner、Trace   |
| `vision`         | `numpy`、`rapidocr_onnxruntime`、`opencv-python`          | OCR 感知（RapidOCR 优先）              |
| `vision-easyocr` | `easyocr`                                               | RapidOCR 不可用时的 OCR 回退            |
| `window`         | `mss`、`pyautogui`、`pygetwindow`                         | 真实窗口截屏与键鼠注入                      |
| `minesweeper`    | `pygame`                                                | `VirtualMinesweeperEnv` / 扫雷游戏本体 |
| `benchmark`      | `pygame`、`numpy`、`rapidocr_onnxruntime`、`opencv-python` | 无头扫雷跑分                           |
| `all`            | 上述全部                                                    | 开发/全功能                           |
| `dev`            | `pytest`、`pytest-asyncio`、`ruff`                        | 测试与静态检查                          |

依赖是**惰性导入**的：核心包可以不带 GUI/OCR/pygame 依赖导入；缺少依赖时会在第一次真正使用对应功能时报 `ImportError`，而不是在 `import game_agent` 时。

常用组合：

```bash
pip install -e ".[benchmark]"       # 无头扫雷 + OCR
pip install -e ".[window,vision]"   # 真实窗口 + OCR
pip install -e ".[all]"             # 全量
```

***

## 10. 库使用注意事项

### 10.1 包名与导入名

- PyPI/安装名：`ai-automate-script`
- 导入名：`game_agent`

```python
from game_agent.framework import AgentRunner
```

另外，`pyproject.toml` 把仓库根目录的 `minesweeper.py` 作为顶层 `minesweeper` 模块一起安装（供 `VirtualMinesweeperEnv` 使用）。如果宿主项目已有同名模块，注意导入冲突；只使用框架核心时不会自动导入它。

### 10.2 `AppSettings` 的输出目录

`AppSettings` 在模块导入时执行 `load_dotenv()`，但 `AppSettings()` 构造时不再创建任何目录。`SCRIPTS_OUTPUT_DIR` 默认是导入 `AppSettings` 时的工作目录下的 `output/`，因此安装到 `site-packages` 后不会往包目录写文件。

如果宿主项目希望指定其他目录，可以在启动前设置环境变量：

```bash
set SCRIPTS_OUTPUT_DIR=D:\my_project\output
```

需要写入时，由调用方自行创建目录：

```python
from game_agent.config.settings import AppSettings

settings = AppSettings()
settings.SCRIPTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
```

`BASE_DIR` 仍保留，但它基于 `settings.py` 的文件位置，仅用于源码级资源定位，不再作为默认输出目录。

如果宿主项目不希望被自动加载 `.env`，可以在导入 `game_agent.config.settings` 之前控制环境变量，或自行构造客户端参数。

### 10.3 异步接口

`AgentRunner.run()` 和 `Decider` 都是异步的：

```python
asyncio.run(runner.run(task))
```

`Environment.capture/act/check/reset` 是同步接口。

### 10.4 `RunTraceLogger` 会清空旧日志

`RunTraceLogger(path)` 初始化时会删除旧日志和同名截图目录。不要把它指向包含其他文件的目录；不需要追踪时传 `None`。

### 10.5 真实窗口模式

- 需要安装 `[window]`；OCR 还需要 `[vision]`，或在 `WindowEnv(use_ocr=False)` 关闭。
- 游戏窗口必须可见，被遮挡可能导致窗口定位/内容评分失败。
- `auto_activate=True` 会尝试把候选窗口带到前台。
- `content_threshold` 和子类 `_content_score()` 用于区分标题相同的干扰窗口。
- `screen_size` 与区域解析每次都跟随窗口移动。

### 10.6 无头扫雷模式

- 需要 `[minesweeper]`（`pygame`）。
- 不需要桌面、不碰鼠标键盘，可多实例并行。
- 游戏逻辑与 `minesweeper.py` 相同，Agent 仍只看渲染像素。
- `VirtualMinesweeperEnv(seed=...)` 支持固定种子复现。

### 10.7 `usage` 的完整性

- `OllamaClient` 会填 token 和耗时。
- `OnlineLLMClient` 当前不填 token；需要成本分析时，应在客户端侧自行采集或使用支持 usage 的端点。
- 自定义 Decider 不设置 `last_usage` 时，`RunResult.usage` 中只有 `calls` 等基础统计。

***

## 11. 常见错误排查

| 错误                                                       | 常见原因                                        | 处理                                                |
| -------------------------------------------------------- | ------------------------------------------- | ------------------------------------------------- |
| `ModuleNotFoundError: game_agent`                        | 未安装包，或不在仓库根目录                               | `pip install -e <项目路径>`                           |
| `ModuleNotFoundError: PIL`                               | 核心依赖缺失                                      | `pip install -e .`                                |
| `ModuleNotFoundError: pygame`                            | 未安装无头扫雷 extras                              | `pip install -e ".[minesweeper]"` 或 `[benchmark]` |
| `ModuleNotFoundError: mss` / `pyautogui` / `pygetwindow` | 未安装窗口 extras                                | `pip install -e ".[window]"`                      |
| OCR 初始化失败                                                | 未安装 `[vision]` 或 RapidOCR 不可用               | 安装 `[vision]`；或 `use_ocr=False`                   |
| `CapabilityError`                                        | 客户端声明不支持 vision/tools                       | 更换支持视觉的模型/端点，或去掉 `function_calling`               |
| `LLMFactoryError`                                        | provider 未知，或 Ollama 传了 `progress_callback` | 检查 `provider` 与后端选项                               |
| `ActionParseError`                                       | 模型输出没有合法动作 JSON                             | 查看 trace；调大 `parse_retries`；检查 prompt/模型能力        |
| 窗口定位失败                                                   | 游戏被遮挡、标题不匹配、未安装窗口 extras                    | 手动点击游戏窗口；检查 `window_title`/`region`               |
| `VirtualMinesweeperEnv` 导入失败                             | 缺少 `pygame` 或 `minesweeper` 模块              | 安装 `[benchmark]`，使用仓库根目录的 `minesweeper.py`        |

***

## 附：相关文档

- [框架设计文档](framework-design.md)
- [项目 README](../README.md)
