import flet as ft
from src.ui.app import AutomateApp

def main(page: ft.Page):
    app = AutomateApp(page)
    app.run()

if __name__ == "__main__":
    # 使用随机端口 (绝对不会冲突，强烈推荐)
    ft.app(target=main, port=0)
