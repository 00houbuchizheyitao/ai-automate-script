"""实证：_som 对全深灰棋盘生成全部 81 个标记（针对 Issue1 的缩进质疑）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import io

from PIL import Image

from src.framework.env.minesweeper_env import MinesweeperEnv

# 全深灰棋盘（全部未翻开）——纯棋盘图，无窗口外框，origin 必须传 (0,0)
img = Image.new("RGB", (360, 360), (100, 100, 100))
buf = io.BytesIO()
img.save(buf, format="PNG")

opened, tags, annotated = MinesweeperEnv._som(buf.getvalue(), origin=(0, 0))
print(f"已翻开格: {len(opened)} 个")
print(f"标记数: {len(tags)} 个（预期 81）")
print(f"标注图字节数: {len(annotated)}（含 81 个品红徽章，应远大于空白棋盘）")
assert len(opened) == 0
assert len(tags) == 81, f"缩进若错只会得到 1 个标记，实际 {len(tags)}"
assert "1" in tags and "81" in tags
print("实证通过：81 个标记全部生成，缩进无问题")
