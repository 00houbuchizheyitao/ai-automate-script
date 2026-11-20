import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class AppSettings:
    APP_NAME = "AI Automate Script"
    APP_VERSION = "1.0.0"
    APP_TITLE = "AI 自动化脚本助手"

    # 源码根目录（editable 安装指向仓库；wheel 安装指向 site-packages）。
    # 仅保留给需要仓库级资源的脚本；输出目录不再基于它。
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    ASSETS_DIR = BASE_DIR / "assets"

    # 输出目录：默认模块导入时的工作目录下的 output/，避免安装到
    # site-packages 后把输出写进包目录。目录不在这里自动创建，
    # 使用前由调用方按需 mkdir。
    SCRIPTS_OUTPUT_DIR = Path(
        os.getenv("SCRIPTS_OUTPUT_DIR", str(Path.cwd() / "output"))
    ).expanduser()

    # LLM 后端选择：ollama | online（online = 任意 OpenAI 兼容 /chat/completions 端点）
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")

    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mimo-v2.6:9b")
    # 上下文与采样：num_ctx 决定 KV cache 大小；thinking 默认开启，单步决策建议关闭
    OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "16384"))
    OLLAMA_TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.2"))
    OLLAMA_TOP_P = float(os.getenv("OLLAMA_TOP_P", "0.9"))
    OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "4096"))
    # default = 不传 think 字段；true/false = 显式开关 thinking
    # 单步决策默认关闭：thinking 会吃掉 num_predict，思考未结束就没有正文
    OLLAMA_THINK = os.getenv("OLLAMA_THINK", "false")
    OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "300"))

    # 在线多模态模型（OpenAI 兼容端点，GLM 开放平台等）
    ONLINE_BASE_URL = os.getenv("ONLINE_BASE_URL", "https://open.bigmodel.cn/api/paas/v4")
    ONLINE_API_KEY = os.getenv("ONLINE_API_KEY", "")
    ONLINE_MODEL = os.getenv("ONLINE_MODEL", "glm-5.3-flash")
    ONLINE_TIMEOUT = int(os.getenv("ONLINE_TIMEOUT", "60"))  # 流式读超时=两次字节最大间隔：挂死几十秒即判定并自动重试（非流式时代的"总等待"语义已废）
    ONLINE_THINKING = os.getenv("ONLINE_THINKING", "off")  # off=禁用思考加速单步决策 / on / low/high/max（始终思考型模型的档位）
    ONLINE_MAX_TOKENS = int(os.getenv("ONLINE_MAX_TOKENS", "0"))  # 0=不传该字段（无框架上限，服务端兜底）；正值=单次生成硬顶

    OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "ch_sim,en").split(",")
    OCR_USE_GPU = os.getenv("OCR_USE_GPU", "false").lower() == "true"

    SCRIPT_PAUSE_INTERVAL = float(os.getenv("SCRIPT_PAUSE_INTERVAL", "0.5"))

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @property
    def scripts_output_dir(self) -> Path:
        return self.SCRIPTS_OUTPUT_DIR
