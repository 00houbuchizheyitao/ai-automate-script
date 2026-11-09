import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class AppSettings:
    APP_NAME = "AI Automate Script"
    APP_VERSION = "0.1.0"
    APP_TITLE = "AI 自动化脚本助手"

    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    ASSETS_DIR = BASE_DIR / "assets"

    SCRIPTS_OUTPUT_DIR = Path(os.getenv("SCRIPTS_OUTPUT_DIR", str(BASE_DIR / "output")))

    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5vl:7b")
    OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "120"))

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

    def __init__(self):
        self.SCRIPTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def scripts_output_dir(self) -> Path:
        return self.SCRIPTS_OUTPUT_DIR
