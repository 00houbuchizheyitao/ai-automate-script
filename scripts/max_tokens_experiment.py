"""实验：max_tokens 预算对"始终思考"模型响应的影响（选默认值用）"""
import asyncio
import base64
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from dotenv import dotenv_values
from PIL import Image

from game_agent.framework.context import ContextAssembler
from game_agent.framework.history import HistoryManager
from game_agent.framework.types import Element, FrameAnalysis, Task

cfg = dotenv_values(Path(__file__).resolve().parent.parent / ".env")
key = cfg["ONLINE_API_KEY"]
url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"


async def run(max_tokens: int, prompt: str, img_b64: str) -> None:
    payload = {"model": "glm-5.3-flash", "stream": False, "max_tokens": max_tokens,
               "thinking": {"type": "enabled", "speed": "low"},
               "messages": [{"role": "user", "content": [
                   {"type": "text", "text": prompt},
                   {"type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"}}]}]}
    t0 = time.time()
    try:
        r = httpx.post(url, headers={"Authorization": f"Bearer {key}"},
                       json=payload, timeout=180)
        dt = time.time() - t0
        d = r.json()
        choice = d["choices"][0]
        content = (choice["message"].get("content") or "")[:80]
        print(f"max_tokens={max_tokens}: {r.status_code} {dt:.1f}s "
              f"finish={choice.get('finish_reason')} "
              f"usage={d.get('usage', {}).get('completion_tokens')} tok")
        print(f"   content={content!r}")
    except Exception as e:
        print(f"max_tokens={max_tokens}: EXC {type(e).__name__} {time.time() - t0:.0f}s")


async def main() -> None:
    img = Image.open(Path(__file__).resolve().parent.parent / "debug_board2.png").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png = buf.getvalue()
    img_b64 = base64.b64encode(png).decode()

    frame = FrameAnalysis(screenshot=png,
                          elements=(Element("1", 149, 169), Element("1", 189, 210)))
    task = Task(goal="屏幕是一个 9×9 的扫雷棋盘。翻开 10 个安全格子。", timeout_steps=20)
    prompt = ContextAssembler().build(task, frame, HistoryManager().view(), (376, 399))
    print("prompt长度:", len(prompt))

    for mt in (2048, 4096):
        await run(mt, prompt, img_b64)


if __name__ == "__main__":
    asyncio.run(main())
