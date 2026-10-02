# 极简扫雷：python minesweeper.py [种子]
# 左键翻开 / 右键插旗 / 中键或左右同按: 一键翻开所有未标记格子 / R 换一局 / ESC 退出
import random
import sys

import pygame as pg

CELL, COLS, ROWS, MINES = 40, 9, 9, 10
W, H = COLS * CELL, ROWS * CELL

NUM_COLORS = {1: (25, 118, 210), 2: (56, 142, 60), 3: (211, 47, 47),
              4: (81, 45, 168), 5: (183, 28, 28), 6: (0, 151, 167),
              7: (33, 33, 33), 8: (117, 117, 117)}


def neighbors(x, y):
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if dx or dy:
                nx, ny = x + dx, y + dy
                if 0 <= nx < COLS and 0 <= ny < ROWS:
                    yield nx, ny


class Game:
    def __init__(self, seed=None):
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        rng = random.Random(self.seed)
        cells = [(x, y) for x in range(COLS) for y in range(ROWS)]
        self.mines = set(rng.sample(cells, MINES))
        self.revealed, self.flagged = set(), set()
        self.result = None  # None / "WIN" / "LOSE"
        self.first_click = True

    def count(self, x, y):
        return sum(n in self.mines for n in neighbors(x, y))

    def reveal(self, x, y):
        if self.result or (x, y) in self.flagged:
            return
        if self.first_click:
            self.first_click = False
            if (x, y) in self.mines:  # 首击踩雷 → 把雷挪到首个空位（首击必安全）
                self.mines.remove((x, y))
                self.mines.add(next(c for c in ((cx, cy)
                                                for cx in range(COLS)
                                                for cy in range(ROWS))
                                    if c not in self.mines and c != (x, y)))
        if (x, y) in self.mines:
            self.result = "LOSE"
            self.revealed |= self.mines
            return
        stack = [(x, y)]
        while stack:
            c = stack.pop()
            if c in self.revealed or c in self.flagged:
                continue
            self.revealed.add(c)
            if self.count(*c) == 0:
                stack.extend(n for n in neighbors(*c) if n not in self.revealed)
        if len(self.revealed) == COLS * ROWS - MINES:
            self.result = "WIN"
            self.flagged |= self.mines

    def toggle_flag(self, x, y):
        if not self.result and (x, y) not in self.revealed:
            self.flagged ^= {(x, y)}

    def clear_unflagged(self):
        """一键翻开所有未插旗的格子：雷旗全对则获胜，插错则踩雷判负"""
        for y in range(ROWS):
            for x in range(COLS):
                if (x, y) not in self.flagged and (x, y) not in self.revealed:
                    self.reveal(x, y)


def draw(screen, g, fonts):
    num_f, big_f, small_f = fonts
    screen.fill((144, 144, 144))
    for y in range(ROWS):
        for x in range(COLS):
            rect = pg.Rect(x * CELL, y * CELL, CELL, CELL)
            if (x, y) in g.revealed:
                pg.draw.rect(screen, (222, 222, 222), rect)
                if (x, y) in g.mines:
                    pg.draw.circle(screen, (211, 47, 47), rect.center, CELL // 4)
                else:
                    n = g.count(x, y)
                    if n:
                        t = num_f.render(str(n), True, NUM_COLORS[n])
                        screen.blit(t, t.get_rect(center=rect.center))
            else:
                pg.draw.rect(screen, (100, 100, 100), rect, 1)
                if (x, y) in g.flagged:
                    pg.draw.polygon(screen, (239, 108, 0), [
                        (rect.centerx - 5, rect.centery - 9),
                        (rect.centerx + 9, rect.centery),
                        (rect.centerx - 5, rect.centery + 9)])
    if g.result:
        overlay = pg.Surface((W, H), pg.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        screen.blit(overlay, (0, 0))
        color = (67, 160, 71) if g.result == "WIN" else (229, 57, 53)
        big = big_f.render(g.result, True, color)
        hint = small_f.render("R / 左键点击: 换一局    ESC: 退出", True, (255, 255, 255))
        screen.blit(big, big.get_rect(center=(W // 2, H // 2 - 20)))
        screen.blit(hint, hint.get_rect(center=(W // 2, H // 2 + 40)))


def main():
    try:
        seed = int(sys.argv[1]) if len(sys.argv) > 1 else None
    except ValueError:
        sys.exit("用法: python minesweeper.py [种子]")
    pg.init()
    screen = pg.display.set_mode((W, H))
    fonts = (pg.font.SysFont("consolas", 24, bold=True),
             pg.font.SysFont("arial", 80, bold=True),
             pg.font.SysFont("microsoftyahei,simhei,arial", 20))
    g = Game(seed)
    pg.display.set_caption(f"扫雷  seed={g.seed}")
    clock = pg.time.Clock()
    pending = None  # 已按下、待抬起时生效的动作 (button, x, y)
    held = set()    # 当前按住的鼠标键（用于识别左右键同按）
    while True:
        for e in pg.event.get():
            if e.type == pg.QUIT or (e.type == pg.KEYDOWN and e.key == pg.K_ESCAPE):
                return
            if e.type == pg.MOUSEBUTTONDOWN and e.button in (1, 2, 3):
                held.add(e.button)
            elif e.type == pg.MOUSEBUTTONUP and e.button in (1, 2, 3):
                held.discard(e.button)
            # R 键重开（兼容输入法拦截场景，额外匹配 unicode）；结算后左键点击也可重开
            restart = e.type == pg.KEYDOWN and (e.key == pg.K_r or getattr(e, "unicode", "") in ("r", "R"))
            if not restart and e.type == pg.MOUSEBUTTONDOWN and e.button == 1 and g.result:
                restart = True
            if restart:
                g = Game()
                pending = None
                pg.display.set_caption(f"扫雷  seed={g.seed}")
            elif e.type == pg.MOUSEBUTTONDOWN and not g.result:
                if e.button == 2 or {1, 3} <= held:
                    g.clear_unflagged()  # 中键或左右同按：一键翻开所有未标记格子
                    pending = None
                else:
                    pending = (e.button, e.pos[0] // CELL, e.pos[1] // CELL)
            elif e.type == pg.MOUSEBUTTONUP and pending and e.button == pending[0] and not g.result:
                btn, x, y = pending
                pending = None
                if btn == 1:
                    g.reveal(x, y)
                elif btn == 3:
                    g.toggle_flag(x, y)
        draw(screen, g, fonts)
        pg.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()
