import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class ScriptSaver:
    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._counter = 0

    def save(self, script_code: str, filename: str | None = None) -> str:
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self._counter += 1
            filename = f"automate_{timestamp}_{self._counter:03d}.py"

        if not filename.endswith(".py"):
            filename += ".py"

        filepath = self.output_dir / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(script_code, encoding="utf-8")
        logger.info(f"脚本已保存至: {filepath}")
        return str(filepath.resolve())
