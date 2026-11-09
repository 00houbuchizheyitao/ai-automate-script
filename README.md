# Game Agent Framework

> 让视觉语言模型只靠「看画面 + 发动作」玩通桌面游戏的最小闭环框架。

**状态**：真实窗口闭环已打通（扫雷）、无头环境可复现跑分、双动作协议可 A/B 对比。v1.0 发布前待补量化基线。

---

## 这个项目要解决什么

让 LLM 直接操作 GUI 有三个绕不开的障碍：

1. **坐标不可靠** — 让模型直接输出像素坐标，误差随分辨率放大，且无法察觉自己点错
2. **输出不合规** — 模型会写错 JSON、漏字段、把推理正文和动作混在一起
3. **没法判定"它到底行不行"** — 单次演示成功不等于有效，必须有可复现的量化基线

本框架用三条设计分别应对：**SoM 编号感知**、**符号解析 + 反馈重试**、**无头环境 + 固定种子跑分**。

---

## 核心设计

### 1. Environment 三方法契约

任何游戏接入框架只需实现三个核心方法（外加一个尺寸属性；跑分场景还需要 `reset()`），框架其余部分零改动：

```python
class Environment(ABC):
    @property
    def screen_size(self) -> tuple[int, int]: ...  # 坐标校验与裁剪
    def capture(self) -> FrameAnalysis: ...         # 给模型看世界
    def act(self, action: Action) -> None: ...      # 让模型动手
    def check(self, task: Task) -> Status: ...      # 裁判哨子
    def reset(self) -> None: ...                    # 跑分场景必须实现
```

`Action` 是游戏无关的键鼠原语词汇表（`key` / `click` / `flag` / `move` / `wait`），`Task` 携带目标声明与成败标准（如"安全翻开 3 格"）。**标准随 Task 传入，机制归 check()** —— 换游戏不用改 Runner。

### 2. SoM（Set-of-Mark）编号感知

不让模型输出坐标，而是让它**报编号**：

- 环境在截图副本上把编号徽章画到每个可交互目标的中心（扫雷即格子中心）
- 同时输出 `编号 → 目标点坐标` 的映射
- 模型只需输出 `{"type": "click", "ids": ["30", "70"]}`
- Runner 负责编号 → 坐标解析；**引用不存在的编号视为解析错误**，错误信息（含可用编号列表）回喂给模型重试

这一步把"空间定位"从模型的弱项里摘了出去，也天然产生了合法性校验——编号不在当前帧，就一定点不到。

### 3. 双动作协议（可 A/B）

同一套上层逻辑，两种 LLM 动作协议可切换对比：

| 协议 | 声明方式 | 约束强度 | 开关 |
|---|---|---|---|
| `prompt-json` | prompt 里写 JSON 格式示例 | 软约束（靠模型遵守） | 默认 |
| `function calling` | API 层 `tools` + JSON Schema | 硬约束（工具声明） | `--fc` |

FC 模式下客户端把返回的 `tool_calls` **序列化回动作 JSON 文本**，因此 `parse_action` 与 SoM 编号解析零改动，两种协议的执行语义完全可比。

### 4. 结论记忆（conclusions）

模型每步可附带"值得下一步复用的推理结论"，例如*"31 和 32 中必有一雷"*：

- 只注入**上一步**的结论（旧结论对当前局面已过时）
- 整局全量累积进 `RunResult.conclusions`，供复盘
- 解析器兼容多种输出形态（随动作对象、独立 JSON 对象、裸键值、标题后裸数组）

### 5. 管道可靠性

- **解析失败不崩循环**：错误信息作为反馈重建 prompt 重试（`parse_retries`，默认 3）
- **僵滞检测**：连续 N 次完全相同的非等待动作 → 注入强警告，要求改变行为
- **流式心跳**：读超时语义 = 两次字节之间的最大间隔，服务端挂死能在几十秒内判定并自动重试一次，无需等满整个生成周期
- **全链路留档**：每次 LLM 调用（含重试）的 prompt、原始输出、解析结果、耗时、截图全部落盘

---

## 架构

```
                    ┌───────────────────────────────────────────────┐
                    │                 AgentRunner                   │
                    │  capture → assemble → decide → act → check    │
                    │                    ↑                          │
                    │            解析失败/僵滞反馈重试                │
                    └───┬──────────┬────────────┬──────────────┬────┘
                        │          │            │              │
              ContextAssembler    │     HistoryManager    RunTraceLogger
                        │          │      (窗口 5 步)      (md + 截图)
                        ▼          ▼
                 FrameAnalysis   Decider（可插拔）
                 截图 + SoM 标注   ├── OnlineLLMClient   在线 VLM（OpenAI 兼容）
                 编号→坐标映射     ├── OllamaClient      本地 VLM
                 可交互元素        └── HumanDecider      人审模式（不调模型）
                        ▲
                        │
                   Environment
                   ├── WindowEnv ──── MinesweeperEnv        真实窗口 + 真实键鼠
                   ├── VirtualMinesweeperEnv                无头 SDL + 进程内事件
                   └── MockEnv                              合成靶子（最小考题）
```

两条链路都对同一套 Runner 接口，因此「真实窗口」与「无头」跑的是同一份决策逻辑，只有事件运输方式不同。

---

## 目录结构

```
src/
├── framework/
│   ├── runner.py                     # 循环编排、重试、僵滞检测
│   ├── context.py                    # prompt 组装（SoM 极简 / 完整两套模板）
│   ├── types.py                      # Action / Task / FrameAnalysis / parse_action
│   ├── history.py                    # 分层历史（窗口切片）
│   ├── som.py                        # 编号徽章绘制 + 坐标映射
│   ├── perception.py                 # 感知层：一帧画面 → FrameAnalysis
│   ├── run_trace.py                  # 追踪日志（markdown + 截图落盘）
│   ├── human_decider.py              # 人审模式：导出"模型将看到的一切"
│   ├── llm_adapter.py                # LLM 客户端 → Decider 协议
│   └── env/
│       ├── base.py                   # Environment 抽象契约
│       ├── window_env.py             # 窗口定位 + 截屏 + 真实键鼠注入
│       ├── minesweeper_env.py        # 扫雷适配（check / reset / 标记）
│       ├── virtual_minesweeper_env.py# 无头扫雷（SDL dummy）
│       └── mock_env.py               # 合成靶子环境
├── llm/
│   ├── online_client.py              # 在线端点：流式、FC、图片重编码
│   └── ollama_client.py              # 本地端点
├── vision/                           # 截屏 / OCR / 图像处理
└── config/settings.py                # .env 配置

scripts/
├── run_minesweeper.py                # 主入口：真实闭环 / 无头 / 人审 / dry-run
├── run_mock_llm.py                   # 基准跑分（N 次，输出统计与 markdown）
├── max_tokens_experiment.py          # 生成长度上限实验
└── ocr_scale_experiment.py           # OCR 缩放实验

minesweeper.py                        # 游戏本体（pygame，9×9 / 10 雷）
tests/                                # 9 个测试文件
```

---

## 快速开始

### 1. 安装

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置

复制 `.env.example` 为 `.env`，按需填写：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ONLINE_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4` | OpenAI 兼容端点 |
| `ONLINE_API_KEY` | （空） | 在线模型密钥，必填才能用 `--llm online` |
| `ONLINE_MODEL` | `glm-5.3-flash` | 在线模型名 |
| `ONLINE_TIMEOUT` | `60` | 流式读超时（两次字节最大间隔，秒） |
| `ONLINE_THINKING` | `off` | `off` / `on` / `low` / `high` / `max` |
| `ONLINE_MAX_TOKENS` | `0` | 0 = 不传该字段，由服务端兜底 |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | 本地端点 |
| `OLLAMA_MODEL` | `qwen2.5vl:7b` | 本地多模态模型 |
| `OCR_LANGUAGES` | `ch_sim,en` | OCR 语言 |

### 3. 跑起来

**无头模式（推荐先跑这个）** —— 进程内运行，不占桌面、不动鼠标，可以边跑边用电脑：

```bash
python scripts/run_minesweeper.py --env virtual --llm online --seed 42
```

**真实窗口模式** —— 需要另开终端启动游戏：

```bash
# 终端 A
python minesweeper.py 42

# 终端 B（运行期间不要移动鼠标/键盘）
python scripts/run_minesweeper.py --env window --llm online
```

**人审模式** —— 不调模型，只导出"模型将看到的完整信息"（原图 + SoM 标注图 + prompt 原文），用于检查感知质量：

```bash
python scripts/run_minesweeper.py --env window --llm human
```

**只看感知不动手**：

```bash
python scripts/run_minesweeper.py --dry-run
```

**双协议对比**：

```bash
python scripts/run_minesweeper.py --env virtual --llm online           # prompt-json
python scripts/run_minesweeper.py --env virtual --llm online --fc      # function calling
```

**本地模型**：

```bash
ollama pull qwen2.5vl:7b
python scripts/run_minesweeper.py --env virtual --llm ollama
```

### 4. 测试

```bash
pytest -q
```

---

## 观测与复盘

每次运行会生成 `llm_views/run_trace/run_trace.md`，逐步记录 prompt、模型原始输出、解析结果、耗时，并把当步截图落盘。另开终端实时跟踪：

```powershell
Get-Content llm_views\run_trace\run_trace.md -Wait -Tail 30
```

失败时这份日志就是唯一的改进依据——能区分「模型推理错」「感知错」「解析错」三种完全不同的故障。

---

## 接入新游戏

1. 继承 `WindowEnv`（窗口游戏）或 `Environment`（自绘/无头）
2. 实现 `capture()`：返回截图，并可选地给出 `tags`（编号→坐标）与 `notes`（画面语义说明）
3. 实现 `act()`：把 `Action` 翻译成真实输入
4. 实现 `check(task)`：判定 SUCCESS / FAIL / RUNNING
5. 实现 `reset()`：跑分场景必需

参考 `src/framework/env/minesweeper_env.py`——它只重写了 `check` / `reset` / `capture` 的增强部分，其余全部继承通用层。

---

## 评测

```bash
python scripts/run_mock_llm.py --runs 10 --save
```

固定种子锁定考题（第 i 次运行的靶位永远一致），统计命中率 / 平均步数 / 解析错误率 / 平均耗时，结果写入 `benchmark_results/`。

### 已有基线：MockEnv × qwen2.5vl:7b

`benchmark_results/baseline_qwen2.5vl_7b_20260927_232910.md`，10 次运行，最大 15 步：

| 指标 | 结果 |
|---|---|
| 命中率 | 8/10 = 80.0% |
| 平均步数（仅自然结束） | 3.9 |
| 解析错误率 | 0/10 = 0.0% |
| 平均耗时 | 7.4 s/次 |

10 次里有 7 次**第一步就命中**；2 次失败的原因都是同一坐标连续重复 15 步——正是僵滞检测要拦的失败模式。

> 该基线只覆盖最简单的合成环境（点击白色方块），用于验证管道可靠性，不代表真实游戏难度。

### 待补：真实闭环基线

<!-- TODO(v1.0): 真实闭环基线待补
     - 环境：VirtualMinesweeperEnv，seed 42..61（20 局）
     - 协议：prompt-json vs function calling
     - 指标：成功率、平均步数、P95 步数、解析错误率、平均耗时、平均调用次数
     - 记录：模型名 + 日期 + 温度
-->

---

## 设计取舍

**为什么不用多 Agent / 编排框架**：单局游戏是实时闭环，加一层调度只增加延迟。任务本身不需要任务分解——需要的是更可靠的单步决策。

**为什么不做 RAG**：状态全在当前帧里，没有"检索历史知识"的需求。历史操作已在 `HistoryManager` 里按窗口切片，结论由 `conclusions` 机制显式携带，两者都受控。

**为什么动作层是键鼠原语而不是游戏语义**：保持 Environment 接口与具体游戏解耦。SoM 编号 + 键鼠原语已经足够表达绝大多数 GUI 操作。

**为什么解析器要容忍多种输出形态**：在线模型的实际输出比 schema 松散得多（裸键值、标题后裸数组、推理正文内含 `{1, 10}` 这类集合记号）。与其假设模型守规矩，不如把解析做成逐段尝试 + 平衡括号扫描。

---

## 已知限制

- `check()` 依赖画面判定，OCR 对手写体/低对比度文字不可靠
- 历史窗口是固定长度切片，没有做摘要压缩
- 无头环境仅扫雷一套；跨环境泛化尚未量化
- Function Calling 仅接入了在线端点（Ollama 工具调用格式不同，未接入）
- 当前为单机单进程，未做并行跑分调度

## Roadmap

- 真实闭环量化基线（20 局 × 双协议）
- 失败模式分类统计（踩雷 / 步数耗尽 / 解析失败 / 非法编号 / 僵滞）
- 机器可读 trace（JSONL）+ 聚合脚本
- 成本与延迟计量（token / 调用次数 / 单步耗时分布）
- 第二个环境接入，验证框架泛化

## License

MIT
