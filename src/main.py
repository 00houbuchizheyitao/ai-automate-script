import flet as ft
from src.ui.app import AutomateApp


def main(page: ft.Page):
    app = AutomateApp(page)
    app.run()


if __name__ == "__main__":
    ft.app(main)
