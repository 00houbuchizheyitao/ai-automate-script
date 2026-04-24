import flet as ft


class AppTheme:
    @staticmethod
    def light_theme() -> ft.Theme:
        return ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=ft.Colors.BLUE_700,
                on_primary=ft.Colors.WHITE,
                secondary=ft.Colors.GREEN_700,
                surface=ft.Colors.GREY_50,
                on_surface=ft.Colors.BLACK87,
            ),
            text_theme=ft.TextTheme(
                body_large=ft.TextStyle(size=14),
                body_medium=ft.TextStyle(size=13),
                label_large=ft.TextStyle(size=14, weight=ft.FontWeight.W_500),
            ),
            visual_density=ft.VisualDensity.COMFORTABLE,
        )

    @staticmethod
    def dark_theme() -> ft.Theme:
        return ft.Theme(
            color_scheme=ft.ColorScheme(
                primary=ft.Colors.BLUE_300,
                on_primary=ft.Colors.BLACK,
                secondary=ft.Colors.GREEN_300,
                surface=ft.Colors.GREY_900,
                on_surface=ft.Colors.WHITE,
            ),
            text_theme=ft.TextTheme(
                body_large=ft.TextStyle(size=14),
                body_medium=ft.TextStyle(size=13),
                label_large=ft.TextStyle(size=14, weight=ft.FontWeight.W_500),
            ),
            visual_density=ft.VisualDensity.COMFORTABLE,
        )
