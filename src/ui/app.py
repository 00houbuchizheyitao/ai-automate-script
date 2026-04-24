import flet as ft

from src.agent.agent import Agent
from src.config.settings import AppSettings
from src.ui.chat_view import ChatView
from src.ui.styles import AppTheme


class AutomateApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.settings = AppSettings()
        self.agent = Agent(self.settings)
        self._init_page()
        self._build_ui()

    def _init_page(self):
        self.page.title = self.settings.APP_TITLE
        self.page.theme = AppTheme.light_theme()
        self.page.dark_theme = AppTheme.dark_theme()
        self.page.theme_mode = ft.ThemeMode.SYSTEM
        self.page.window.width = 900
        self.page.window.height = 700
        self.page.window.min_width = 600
        self.page.window.min_height = 500
        self.page.window.center()
        self.page.padding = 0

    def _build_ui(self):
        self.chat_view = ChatView(self.page, self.agent)
        self.page.add(self.chat_view)

    def run(self):
        pass
