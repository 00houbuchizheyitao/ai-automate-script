import flet as ft


class MessageBubble(ft.Container):
    def __init__(self, role: str, text: str, image_base64: str | None = None):
        self.role = role
        self.text = text
        self.image_base64 = image_base64

        is_user = role == "user"
        bg_color = ft.Colors.BLUE_50 if is_user else ft.Colors.GREY_100
        alignment = ft.alignment.top_right if is_user else ft.alignment.top_left

        content_controls = []
        if image_base64:
            content_controls.append(
                ft.Image(src_base64=image_base64, width=280, fit=ft.ImageFit.CONTAIN)
            )
        if text:
            content_controls.append(ft.Text(text, selectable=True))

        super().__init__(
            content=ft.Column(controls=content_controls, spacing=5),
            bgcolor=bg_color,
            border_radius=10,
            padding=12,
            alignment=alignment,
            width=400,
        )
