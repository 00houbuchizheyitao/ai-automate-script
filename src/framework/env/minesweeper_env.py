"""扫雷环境适配器：框架接入第一个真实窗口游戏。

游戏本体：仓库根目录 minesweeper.py（pygame，9×9 / 10 雷，40px 格子，
窗口标题 "扫雷  seed=..."，结算时画面中央渲染大号 WIN / LOSE）。

适配者只需实现 check/reset——capture/act/screen_size 全部继承 WindowEnv，
验证"桌面游戏通用层"的设计承诺。

坐标约定：
- LLM 视角：region 内图像坐标（与 WindowEnv 一致）
- 游戏棋盘：COLS×ROWS 格子，每格 CELL 像素，棋盘铺满整个窗口
- board_cell(): 图像坐标 → (col, row)，供 check 内部换算用
"""
from __future__ import annotations

import time

from src.framework.env.window_env import WindowEnv
from src.framework.som import SomTag, draw_som_tags
from src.framework.types import Action, FrameAnalysis, Status, Task

COLS, ROWS, CELL = 9, 9, 40
BOARD = (COLS * CELL, ROWS * CELL)  # (360, 360)
# 棋盘在窗口图像内的偏移：外框含标题栏与边框（Win11 实测 ~31px/~8px）。
# 若分类错位（所有格子被判成同一状态），用构造参数校正。
DEFAULT_BOARD_ORIGIN = (8, 31)
BRIGHTNESS_THRESHOLD = 160  # <160 深灰=未翻开；>=160 浅色=已翻开


class MinesweeperEnv(WindowEnv):
    """扫雷适配器。

    参数:
        window_title: 窗口标题子串，默认 "扫雷"（跟随窗口移动）
        settle_s: 动作后等待游戏渲染的时长（连锁翻格需要一点时间）
    任务约定（Task.meta）:
        safe_opens: 需安全翻开的格子数（默认 3）
    """

    def __init__(self, window_title: str = "扫雷",
                 settle_s: float = 0.35, board_origin: tuple[int, int] | None = None,
                 **kwargs):
        kwargs.setdefault("region", (0, 0, *BOARD))
        super().__init__(window_title=window_title, **kwargs)
        self.settle_s = settle_s
        self.board_origin = board_origin or DEFAULT_BOARD_ORIGIN
        self._title_bar_h = 40  # 真实窗口截图含标题栏，已翻格计数时排除
        self._flagged: set[str] = set()  # LLM 推理标记的雷格编号（整局累积）

    # ---------- 坐标换算 ----------

    @staticmethod
    def board_cell(x: int, y: int) -> tuple[int, int]:
        """图像坐标 → 棋盘 (col, row)；越界返回 (-1, -1)。"""
        if not (0 <= x < BOARD[0] and 0 <= y < BOARD[1]):
            return (-1, -1)
        return (x // CELL, y // CELL)

    # ---------- Environment 契约 ----------

    def capture(self) -> FrameAnalysis:
        frame = super().capture()
        opened, tags, annotated = self._som(frame.screenshot,
                                            flagged=self._flagged)
        # 环境自解释：格子状态的颜色语义 + SoM/旗子说明（MockEnv 红点说明的先例）
        note = ("棋盘为 9×9 格子铺满整个窗口（每格 40 像素）。"
                "深灰色格子 = 未翻开（可以点击或标记）；"
                "浅色格子 = 已翻开（上面可能显示数字），不可再点；"
                "橙色三角 = 你此前推理出的雷格标记。"
                "第二张图是 SoM 编号标注图（未翻开的格子中间有品红编号徽章），"
                "点击或标记深灰格子直接引用其编号。")
        notes = f"{frame.notes}；{note}" if frame.notes else note
        return FrameAnalysis(screenshot=frame.screenshot,
                             elements=frame.elements, notes=notes,
                             annotated=annotated, tags=tags,
                             opened_ids=frozenset(opened))

    def act(self, action: Action) -> None:
        if action.type == "flag":
            self._flag(action)
            return
        super().act(action)
        time.sleep(self.settle_s)  # 连锁翻格/结算画面需要渲染时间

    def _flag(self, action: Action) -> None:
        """标记雷格：仅更新内部标记集合（驱动 SoM 橙三角），不注入键鼠。

        游戏内的右键插旗对 Agent 判定无影响（Agent 不使用旗子信息），
        且右键注入有误触菜单风险——标记以纯视觉反馈呈现。
        """
        for tid in action.ids or ([action.id] if action.id else []):
            self._flagged.add(tid)
        time.sleep(self.settle_s)

    def click_cell(self, col: int, row: int) -> None:
        """无头模式的便捷点击：左键翻开 (col,row) 格。"""
        self.act(Action(type="click", x=col * 40 + 20, y=row * 40 + 20))

    def check(self, task: Task) -> Status:
        """判定：OCR 找大号 WIN/LOSE 结算字样，否则数已翻安全格。"""
        frame = self.capture()
        texts = [e.text.strip().upper() for e in frame.elements]

        if any("LOSE" in t for t in texts):
            return Status.FAIL
        if any("WIN" in t for t in texts):
            return Status.SUCCESS

        # 无结算画面：统计已翻开的安全格数（数字格 + 空白格都是安全翻开）
        need = int(task.meta.get("safe_opens", 3))
        if self._opened_cells(frame) >= need:
            return Status.SUCCESS
        return Status.RUNNING

    def reset(self) -> None:
        """重开一局：结算画面按 R 键；无结算画面时 R 也直接开新局。"""
        self.act(Action(type="key", key="r"))
        time.sleep(self.settle_s)


    # ---------- SoM：格子分类与编号标注 ----------

    @classmethod
    def _som(cls, screenshot: bytes,
             origin: tuple[int, int] | None = None,
             flagged: set[str] | None = None
             ) -> tuple[set[str], dict[str, tuple[int, int]], bytes]:
        """按格子平均亮度分类格子状态，输出 SoM 标注。

        纯函数（无窗口依赖）。编号按几何位置固定（row*9+col+1），不随
        格子状态变化——同一格子的编号在整局游戏中保持稳定。
        返回 (已翻开格编号集合, 未翻开格编号→中心坐标映射, 标注图字节)；
        标注图只做两件事：未翻开格画品红编号徽章（SoM 唯一职责），
        flagged 中的编号画橙色三角（雷标记，已翻开的跳过）。
        """
        import io

        import numpy as np
        from PIL import Image, ImageDraw, ImageFont

        img = Image.open(io.BytesIO(screenshot)).convert("RGB")
        arr = np.asarray(img, dtype=np.float32)
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype(r"C:\Windows\Fonts\consola.ttf", 14)
        except OSError:
            font = ImageFont.load_default()
        ox, oy = origin or DEFAULT_BOARD_ORIGIN
        ih, iw = arr.shape[:2]
        opened: set[str] = set()
        tags_map: dict[str, tuple[int, int]] = {}
        som_tags: list[SomTag] = []
        for row in range(ROWS):
            for col in range(COLS):
                cx = ox + col * CELL + CELL // 2   # 格子中心（图像坐标）
                cy = oy + row * CELL + CELL // 2
                # 采样窗 clamp 到图像边界：真实窗口截图边缘格子（棋盘原点
                # 偏移导致采样窗越界）会切出空数组产生 NaN，误判格子状态
                x0, x1 = max(0, cx - 10), min(iw, cx + 10)
                y0, y1 = max(0, cy - 10), min(ih, cy + 10)
                if x0 >= x1 or y0 >= y1:
                    continue  # 格子中心完全在图像外 → 无法采样，跳过
                patch = arr[y0:y1, x0:x1]
                tid = str(row * COLS + col + 1)
                if patch.mean() >= BRIGHTNESS_THRESHOLD:  # 浅色 → 已翻开，不打标记
                    opened.add(tid)
                else:                                     # 深灰 → 未翻开 → 编号徽章
                    tags_map[tid] = (cx, cy)
                    som_tags.append(SomTag(id=tid, x=cx, y=cy))
        for tid in (flagged or ()):  # 推理出的雷格 → 橙色三角（覆盖在原画面上）
            if tid in opened:
                continue  # 已翻开的格子不再画雷标记
            col, row = (int(tid) - 1) % COLS, (int(tid) - 1) // COLS
            cx, cy = ox + col * CELL + CELL // 2, oy + row * CELL + CELL // 2
            draw.polygon([(cx, cy - 9), (cx + 8, cy), (cx, cy + 9)],
                         fill=(239, 108, 0))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        # 编号徽章最后统一叠加（SoM 工具绘制：徽章画在格子中心，
        # 贴边的第一行/列序号不会被截图边缘裁掉）
        return opened, tags_map, draw_som_tags(buf.getvalue(), som_tags)

    # ---------- 内容校验：以游戏实际画面为参照物 ----------

    BOARD_GRAYS = ((100, 100, 100),   # 未翻开格
                   (144, 144, 144),   # 背景
                   (222, 222, 222))   # 已翻开格

    def _content_score(self, png: bytes) -> float:
        """颜色签名评分：中央区域落在棋盘三种灰色的像素占比。

        扫雷窗口画面几乎 100% 由这三种灰构成；对话/IDE/网页等标题恰含
        "扫雷"的干扰窗口是白底彩字或深底，得分接近 0。颜色直方图对窗口
        缩放不敏感，比模板匹配更稳。
        """
        import io

        import numpy as np
        from PIL import Image

        img = np.asarray(Image.open(io.BytesIO(png)).convert("RGB"), dtype=np.int16)
        h, w, _ = img.shape
        if h < 100 or w < 100:
            return 0.0
        center = img[h // 4: 3 * h // 4, w // 4: 3 * w // 4].reshape(-1, 3)
        close = sum(int((np.abs(center - np.array(g)).sum(axis=1) <= 24).sum())
                    for g in self.BOARD_GRAYS)
        return close / len(center)

    # ---------- 内部 ----------

    def _opened_cells(self, frame) -> int:
        """估算已翻开格数：OCR 到的数字格各占一格（粗估，够判定用）。

        连锁翻开的空白格没有数字，OCR 读不到——所以这个计数偏保守。
        判定策略：数字格数 ≥ need 即视为达标（空白格只会更多）。
        标题栏区域（含 "seed=42" 字样）被排除——无头渲染没有标题栏，
        _title_bar_h=0 即不过滤。
        """
        seen: set[tuple[int, int]] = set()
        for e in frame.elements:
            text = e.text.strip()
            if e.y < self._title_bar_h:  # 真实窗口=排除标题栏 seed=42 误读
                continue
            if text.isdigit() and 1 <= int(text) <= 8:
                cell = MinesweeperEnv.board_cell(e.x, e.y)
                if cell != (-1, -1):
                    seen.add(cell)
        return len(seen)
