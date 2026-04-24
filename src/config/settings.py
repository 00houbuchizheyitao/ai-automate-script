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

    OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "ch_sim,en").split(",")
    OCR_USE_GPU = os.getenv("OCR_USE_GPU", "false").lower() == "true"

    SCRIPT_PAUSE_INTERVAL = float(os.getenv("SCRIPT_PAUSE_INTERVAL", "0.5"))

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    def __init__(self):
        self.SCRIPTS_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def scripts_output_dir(self) -> Path:
        return self.SCRIPTS_OUTPUT_DIR
