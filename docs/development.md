# 开发指南

## 开发环境搭建

### 1. 基础环境

- **Python**: 3.10+（推荐 3.11）
- **Git**: 最新版
- **Ollama**: [下载安装](https://ollama.ai/)

### 2. 项目初始化

```bash
# 克隆项目
git clone <repository-url>
cd ai_automate_script

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # Linux/macOS

# 安装依赖（含开发依赖）
pip install -r requirements.txt

# 安装 pre-commit hooks（可选）
pip install ruff
```

### 3. Ollama 模型准备

```bash
# 安装并启动 Ollama
ollama serve

# 拉取 Qwen2.5-VL-7B 模型
ollama pull qwen2.5vl:7b

# 验证模型可用
ollama list
```

### 4. 环境变量配置

```bash
copy .env.example .env
```

根据本地环境修改 `.env` 文件中的配置项，特别是 `SCRIPTS_OUTPUT_DIR`（脚本输出路径）。

---

## 项目架构详解

### 分层设计

项目采用**三层架构**设计，各层职责明确、松耦合：

```
用户交互层 (ui/)  ←→  Agent 编排层 (agent/)  ←→  基础能力层 (llm/, vision/, script/)
```

#### 用户交互层 (`src/ui/`)

基于 Flet 框架构建的聊天式界面，负责：

- 接收用户文字输入（必填）和截图附件（可选）
- 展示 Agent 响应（包含脚本保存路径）
- 截图作为可选附件，用户先添加截图再输入文字一起发送

关键文件：

- `app.py` — 主应用初始化，配置页面属性和主题
- `chat_view.py` — 聊天主界面，支持截图暂存 + 文字输入 + 一起发送
- `components/` — 可复用 UI 组件（message_bubble, screenshot_upload）

#### Agent 编排层 (`src/agent/`)

核心业务逻辑层，负责：

- **对话优先**：首先与用户对话，确认意图。
- **按需生成**：只有在用户明确要求时才生成脚本。
- **截图分析**：调用视觉能力，识别用户标注。
- **脚本保存**：识别生成的自动化代码块（含 `pyautogui`, `keyboard` 等）并自动保存。

关键文件：

- `agent.py` — Agent 主编排器，统一处理纯文字和文字+截图两种模式
- `graph.py` — LangGraph 工作流定义（MVP 预留）
- `prompts/` — 所有 Prompt 模板集中管理
- `tools/` — Agent 可调用的工具集

#### 基础能力层 (`src/llm/`, `src/vision/`, `src/script/`)

提供底层能力，被 Agent 层调用：

| 模块 | 职责 | 关键依赖 |
|------|------|---------|
| `llm/` | LLM 调用抽象与实现 | httpx, ollama |
| `vision/` | 图像处理与文字识别 | EasyOCR, mss, OpenCV |
| `script/` | 脚本生成、校验、保存 | pyautogui |

---

## 关键设计决策

### 1. 截图是可选的

用户交互的核心是**自然语言**，截图仅在文字难以描述时使用：

- 纯文字模式：用户直接描述任务 → LLM 生成脚本
- 截图辅助模式：用户上传带标注的截图 + 文字描述 → OCR + VLM 分析 → LLM 生成脚本

截图的典型使用场景：
- 用户圈出某个按钮 → Agent 理解为"点击该按钮"
- 用户用箭头指向某区域 → Agent 理解为"操作该区域的元素"
- 用户高亮某段文字 → Agent 理解为"针对该文字相关元素操作"

实现方式：
- `chat_view.py` 中截图先暂存为 `_pending_image_bytes`
- 用户输入文字后一起发送，通过 `agent.set_pending_image()` 传递
- `agent.py` 中 `process()` 方法根据是否有 pending image 自动选择处理路径

### 2. LLM 抽象层

`src/llm/base.py` 定义了 `BaseLLMClient` 抽象基类，所有 LLM 实现都必须继承此类。这确保了：

- MVP 阶段使用 Ollama 本地模型
- 未来可无缝切换到在线大模型（OpenAI / Claude / Gemini）
- 业务代码不依赖具体 LLM 实现

```python
# 切换 LLM 只需修改 Agent 初始化
# MVP:
self.llm = OllamaClient(settings)
# 未来:
self.llm = OnlineLLMClient(api_key=..., model="gpt-4o")
```

### 3. 脚本直接保存，不预览不运行

生成的脚本直接保存到用户配置的输出路径（`SCRIPTS_OUTPUT_DIR`），用户自行运行验证：

- `ScriptSaver` 类负责保存脚本，自动生成带时间戳的文件名
- Agent 响应中告知用户脚本保存路径
- 用户到输出目录找到脚本，自行 `python xxx.py` 运行

这样设计的原因：
- 小白用户不需要理解代码，只需双击运行
- 避免在应用内执行自动化脚本的安全风险
- 用户可以反复运行和修改脚本

### 4. Prompt 模板管理

所有 Prompt 集中在 `src/agent/prompts/` 目录管理，使用 Python 字符串模板：

- `system_prompt.py` — Agent 系统人设、截图标注识别规范
- `script_generation.py` — 脚本生成（含截图/纯文字两种模板）和修正的 Prompt

### 5. 脚本安全与权限机制

生成的脚本包含以下保障：

- **自动提权**：如果脚本涉及键盘监听（`keyboard` 库），会自动请求管理员权限运行，以确保钩子生效。
- **安全退出**：`pyautogui.FAILSAFE = True` — 鼠标移至屏幕角落可紧急停止。
- **路径适配**：提权逻辑已处理路径空格问题，确保在各种安装路径下都能正常工作。
- **安全校验**：`ScriptValidator` 检测危险调用（如 `os.system`）。

### 6. 脚本模板系统

`src/script/templates/` 提供脚本骨架模板，LLM 生成的代码填充到模板中，确保：

- 统一的代码结构
- 必要的导入和异常处理
- 一致的日志和配置

---

## 开发规范

### 代码风格

- 使用 `ruff` 作为代码格式化和 lint 工具
- 行宽上限 100 字符
- Python 3.10+ 特性（`|` 类型联合、`match` 语句等）

```bash
# 格式化
ruff format src/ tests/

# Lint 检查
ruff check src/ tests/
```

### 命名规范

| 类型 | 风格 | 示例 |
|------|------|------|
| 模块/包 | snake_case | `screen_capture.py` |
| 类 | PascalCase | `OllamaClient` |
| 函数/方法 | snake_case | `extract_text()` |
| 常量 | UPPER_SNAKE | `DEFAULT_RESOLUTION` |
| 私有方法 | _前缀 | `_build_messages()` |

### 异步编程

- 所有 LLM 调用和 I/O 操作使用 `async/await`
- Flet 事件处理使用异步函数
- 使用 `httpx.AsyncClient` 替代 `requests`

### 测试规范

```bash
# 运行全部测试
pytest

# 运行指定模块测试
pytest tests/test_agent.py

# 带覆盖率
pytest --cov=src tests/
```

测试要求：

- 每个模块至少包含基本初始化测试
- LLM 相关测试使用 mock，不依赖真实模型
- 关键业务逻辑需要覆盖正常和异常路径

---

## 常见开发任务

### 添加新的 Agent 工具

1. 在 `src/agent/tools/` 下创建新工具文件
2. 实现工具类，接收 `BaseLLMClient` 作为依赖
3. 在 `src/agent/agent.py` 中注册工具
4. 添加对应的 Prompt 模板（如需要）
5. 编写测试

### 添加新的 LLM 后端

1. 在 `src/llm/` 下创建新客户端文件
2. 继承 `BaseLLMClient`，实现三个抽象方法
3. 在 `src/config/settings.py` 中添加配置项
4. 在 `src/agent/agent.py` 中根据配置选择客户端

### 添加新的脚本模板

1. 在 `src/script/templates/` 下创建模板文件
2. 定义模板字符串，使用 `{variable}` 占位符
3. 在 `ScriptGenerator` 中集成模板选择逻辑
4. 编写模板渲染测试

### 修改 Prompt

1. 在 `src/agent/prompts/` 下找到对应文件
2. 修改 Prompt 文本
3. 运行测试确保格式正确
4. 手动验证生成效果

---

## 打包与发布

### 1. 打包可执行文件

```bash
# 使用 flet pack
flet pack src/main.py \
    --name ai_automate_script \
    --icon assets/icons/app.ico \
    --add-data "assets;assets"

# 或使用 PyInstaller
pyinstaller --name ai_automate_script \
    --windowed \
    --icon assets/icons/app.ico \
    --add-data "assets;assets" \
    src/main.py
```

### 2. 创建安装程序

1. 安装 [Inno Setup](https://jrsoftware.org/isinfo.php)
2. 根据需要修改 `scripts/build_installer.iss`
3. 在 Inno Setup IDE 中编译安装脚本
4. 安装程序输出到 `dist/` 目录
5. 安装程序允许用户自选安装路径，脚本输出目录默认为安装目录下的 `output/`

### 3. 发布检查清单

- [ ] 更新 `pyproject.toml` 中的版本号
- [ ] 更新 `scripts/build_installer.iss` 中的版本号
- [ ] 运行全部测试通过
- [ ] 手动测试核心流程
- [ ] 检查打包后程序运行正常
- [ ] 检查安装程序流程
- [ ] 验证脚本输出路径配置正确

---

## 已知限制（MVP）

1. **Qwen2.5-VL-7B 本地推理速度较慢**，首次响应可能需要 30-60 秒
2. **OCR 准确率受截图质量影响**，低分辨率截图识别效果差
3. **截图标注识别依赖 VLM 能力**，复杂标注可能识别不准
4. **生成的脚本坐标基于特定分辨率**，不同分辨率需要调整
5. **pyautogui 依赖屏幕坐标**，窗口位置变化会导致脚本失效
6. **LangGraph 工作流尚未实现**，脚本生成准确率有待提升

---

## 路线图

### Phase 1 — MVP（当前）

- [x] 项目结构搭建
- [x] Flet 聊天 UI（截图可选）
- [x] Ollama + Qwen2.5-VL 集成
- [x] EasyOCR 文字识别
- [x] 截图标注识别
- [x] 基础脚本生成
- [x] 脚本自动保存到用户指定路径
- [ ] 端到端流程调通
- [ ] 打包与安装程序

### Phase 2 — 增强

- [ ] LangGraph 多步骤工作流
- [ ] 脚本校验与自动修正循环
- [ ] 在线大模型支持
- [ ] 脚本录制回放
- [ ] 多语言界面（i18n）

### Phase 3 — 扩展

- [ ] 安卓支持
- [ ] iOS 支持
- [ ] 脚本市场 / 模板库
- [ ] 用户反馈学习
