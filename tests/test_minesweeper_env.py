"""MinesweeperEnv 单元测试：坐标换算/OCR过滤/内容评分（不依赖游戏窗口）。"""
import io

import pytest
from PIL import Image, ImageDraw

from src.framework.env.minesweeper_env import MinesweeperEnv
from src.framework.types import Element, FrameAnalysis, Status, Task


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_board_cell_translation():
    assert MinesweeperEnv.board_cell(0, 0) == (0, 0)
    assert MinesweeperEnv.board_cell(39, 39) == (0, 0)      # 第0格右下角
    assert MinesweeperEnv.board_cell(40, 0) == (1, 0)       # 第1列
    assert MinesweeperEnv.board_cell(185, 339) == (4, 8)    # 中心偏下
    assert MinesweeperEnv.board_cell(360, 180) == (-1, -1)  # 越界
    assert MinesweeperEnv.board_cell(-1, 10) == (-1, -1)


def test_opened_cells_counts_digit_cells():
    """数字格计数：同格多读只算一次，非数字与标题栏区元素忽略"""
    env = MinesweeperEnv()
    frame = FrameAnalysis(
        screenshot=b"",
        elements=(Element(text="1", x=20, y=60),      # (0,1) 棋盘区
                  Element(text="2", x=60, y=60),      # (1,1)
                  Element(text="2", x=62, y=65),      # 同格重复 → 去重
                  Element(text="WIN", x=180, y=180),  # 非数字 → 忽略
                  Element(text="旗", x=100, y=100),   # 非数字 → 忽略
                  Element(text="42", x=150, y=15)),   # 标题栏 seed=42 → 排除
    )
    assert env._opened_cells(frame) == 2
    assert env._opened_cells(FrameAnalysis(screenshot=b"")) == 0


def test_content_score_separates_game_from_ide():
    """内容评分：仿游戏画面（棋盘三灰）高分，仿 IDE 白底画面低分"""
    env = MinesweeperEnv()

    game = Image.new("RGB", (376, 399), (144, 144, 144))
    d = ImageDraw.Draw(game)
    for gy in range(9):
        for gx in range(9):
            d.rectangle([gx * 40, gy * 40, gx * 40 + 39, gy * 40 + 39],
                        fill=(100, 100, 100))
    assert env._content_score(_png(game)) > 0.8

    ide = Image.new("RGB", (376, 399), (255, 255, 255))  # 白底 IDE/对话画面
    d = ImageDraw.Draw(ide)
    for y in range(20, 380, 30):
        d.text((10, y), "runner = AgentRunner 123456", fill=(30, 30, 30))
    assert env._content_score(_png(ide)) < 0.3
