# AI Automate Script

> 智能自动化脚本生成 Agent — 通过自然语言（可选截图），让小白用户也能获得可直接运行的桌面自动化脚本

## 项目简介

AI Automate Script 是一个基于视觉语言模型的智能 Agent，用户通过自然语言描述任务即可获得可直接运行的 Python 自动化脚本。当文字难以描述时（如"点击这个按钮"），用户可以上传带标注的截图，Agent 会理解标注意图并生成对应脚本。

**核心价值**：零编程门槛 → 对话即脚本 → 直接运行完成任务

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                    用户交互层 (Flet UI)                    │
│  ┌───────────────────┐  ┌──────────────────────────┐    │
│  │ 自然语言输入       │  │ 截图附件（可选）          │    │
│  │ (必填)            │  │ (圈出按钮/箭头指向等)     │    │
│  └────────┬──────────┘  └────────────┬─────────────┘    │
└───────────┼──────────────────────────┼──────────────────┘
            │                          │
            ▼                          ▼
┌─────────────────────────────────────────────────────────┐
│                    Agent 编排层                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ 截图分析      │  │ 意图理解      │  │ 脚本生成      │  │
│  │ (OCR+VLM)   │  │ (LLM)       │  │ (LLM+模板)   │  │
│  │ 识别标注意图  │  │              │  │              │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│  ┌──────────────────────────────────────────────────┐   │
│  │ LangGraph 工作流 (规划 → 生成 → 校验 → 修正)      │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
            │                          │
            ▼                          ▼
┌─────────────────────────────────────────────────────────┐
│                    基础能力层                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────┐  │
│  │ Ollama   │  │ EasyOCR  │  │ mss      │  │ OpenCV │  │
│  │ (Qwen2.5│  │ (文字识别)│  │ (截屏)   │  │(图像匹配)│ │
│  │  -VL-7B)│  │          │  │          │  │        │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────┘  │
│  ┌──────────────────────────────────────────────────┐   │
│  │ pyautogui + keyboard (自动化与热键) + ScriptSaver │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| UI | Flet | 跨平台桌面/移动端 UI 框架 |
| LLM | Ollama + Qwen2.5-VL-7B | 本地视觉语言模型 |
| OCR | EasyOCR | 中英文文字识别 |
| 截屏 | mss | 高性能屏幕截图 |
| 图像匹配 | OpenCV | 模板匹配定位界面元素 |
| 自动化 | pyautogui / keyboard | 鼠标键盘模拟与热键监听 |
| Agent 工作流 | LangGraph | 多步骤脚本生成流程（规划中） |
| 打包 | flet pack / PyInstaller | 可执行文件打包 |
| 安装程序 | Inno Setup | 专业 Windows 安装程序 |

## 项目结构

```
ai_automate_script/
├── src/
│   ├── main.py                     # 应用入口
│   ├── ui/                         # Flet 前端界面层
│   │   ├── app.py                  # 主应用
│   │   ├── chat_view.py            # 聊天界面（截图可选）
│   │   ├── components/             # UI 组件
│   │   │   ├── message_bubble.py   # 消息气泡
│   │   │   └── screenshot_upload.py # 截图上传
│   │   └── styles.py               # 主题样式
│   ├── agent/                      # Agent 核心逻辑
│   │   ├── agent.py                # Agent 编排器
│   │   ├── graph.py                # LangGraph 工作流
│   │   ├── prompts/                # Prompt 模板
│   │   │   ├── system_prompt.py    # 系统提示词
│   │   │   └── script_generation.py # 脚本生成提示词
│   │   └── tools/                  # Agent 工具
│   │       ├── screenshot_analyzer.py # 截图分析（含标注识别）
│   │       └── script_generator.py    # 脚本生成
│   ├── llm/                        # LLM 集成层
│   │   ├── base.py                 # 抽象基类
│   │   ├── ollama_client.py        # Ollama 实现
│   │   └── online_client.py        # 在线大模型（预留）
│   ├── vision/                     # 视觉处理层
│   │   ├── ocr.py                  # EasyOCR 集成
│   │   ├── screen_capture.py       # mss 截屏
│   │   └── image_processor.py      # OpenCV 图像处理
│   ├── script/                     # 脚本生成与保存
│   │   ├── generator.py            # 脚本生成
│   │   ├── executor.py             # 脚本保存（ScriptSaver）
│   │   ├── templates/              # 脚本模板
│   │   │   ├── base_template.py    # 基础模板
│   │   │   └── gui_automation.py   # GUI 自动化模板
│   │   └── validator.py            # 脚本校验
│   └── config/                     # 配置管理
│       ├── settings.py             # 应用设置
│       └── constants.py            # 常量定义
├── assets/                         # 静态资源
├── tests/                          # 测试套件
├── scripts/                        # 构建脚本
│   └── build_installer.iss         # Inno Setup 安装脚本
├── docs/                           # 项目文档
│   └── development.md              # 开发指南
├── requirements.txt                # Python 依赖
├── pyproject.toml                  # 项目元数据
├── .gitignore
├── .env.example                    # 环境变量模板
└── README.md
```

## 快速开始

### 环境要求

- Python 3.10+
- [Ollama](https://ollama.ai/) 已安装并运行
- Windows 10/11

### 安装步骤

1. **克隆项目**
```bash
git clone <repository-url>
cd ai_automate_script
```

2. **创建虚拟环境**
```bash
python -m venv .venv
.venv\Scripts\activate
```

3. **安装依赖**
```bash
pip install -r requirements.txt
```

4. **安装 Ollama 模型**
```bash
ollama pull qwen2.5vl:7b
```

5. **配置环境变量**
```bash
copy .env.example .env
# 根据需要修改 .env 中的配置，特别是 SCRIPTS_OUTPUT_DIR
```

6. **启动应用**
```bash
python -m src.main
```

### 打包发布

```bash
# 使用 flet pack 打包
flet pack src/main.py --name ai_automate_script --icon assets/icons/app.ico

# 使用 Inno Setup 创建安装程序
# 在 Inno Setup 中编译 scripts/build_installer.iss
# 安装程序允许用户自选安装路径，脚本输出目录默认为安装目录下的 output/
```

## 核心流程

1. **用户输入**：用自然语言进行交流或描述任务。
2. **对话交互**：Agent 优先以对话形式回答用户。
3. **意图确认**：只有当用户明确要求（如“帮我写个脚本”）时，Agent 才进入生成流程。
4. **截图分析**（如有截图）：EasyOCR 提取文字 → Qwen2.5-VL 分析界面元素和用户标注。
5. **脚本生成**：基于模板 + LLM 生成包含自动化逻辑（及热键监听，如适用）的 Python 脚本。
6. **脚本保存**：自动保存到用户配置的输出路径。
7. **用户运行**：用户自行到输出目录运行脚本。如果涉及热键监听，脚本会自动请求管理员权限。

## 截图使用场景

截图是**可选的**，主要用于以下场景：

| 场景 | 示例 |
|------|------|
| 用户圈出按钮 | "点击这个按钮" + 圈出截图中的按钮 |
| 用户箭头指向区域 | "在这个位置输入文字" + 箭头指向输入框 |
| 用户高亮元素 | "选择这个选项" + 高亮下拉菜单项 |
| 纯文字描述 | "打开记事本并输入Hello" + 无需截图 |

## MVP 范围

### MVP 包含
- ✅ Flet 聊天 UI（自然语言输入 + 可选截图附件）
- ✅ Ollama + Qwen2.5-VL-7B 本地推理
- ✅ EasyOCR 文字识别
- ✅ 截图标注识别（圈出/箭头/高亮）
- ✅ pyautogui 脚本生成
- ✅ 脚本自动保存到用户指定路径
- ✅ 基础脚本校验

### MVP 后规划
- 🔲 LangGraph 多步骤工作流（规划 → 生成 → 校验 → 修正循环）
- 🔲 在线大模型支持（OpenAI / Claude / Gemini）
- 🔲 脚本录制回放
- 🔲 安卓 / iOS 支持
- 🔲 多语言界面（i18n）
- 🔲 脚本市场 / 模板库

## 配置说明

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API 地址 |
| `OLLAMA_MODEL` | `qwen2.5vl:7b` | 使用的模型名称 |
| `OLLAMA_TIMEOUT` | `120` | 请求超时时间（秒） |
| `OCR_LANGUAGES` | `ch_sim,en` | OCR 识别语言 |
| `OCR_USE_GPU` | `false` | 是否启用 GPU 加速 OCR |
| `SCRIPTS_OUTPUT_DIR` | `./output` | 脚本输出路径（安装时自选） |
| `SCRIPT_PAUSE_INTERVAL` | `0.5` | 脚本操作间隔（秒） |
| `LOG_LEVEL` | `INFO` | 日志级别 |

## License

MIT
