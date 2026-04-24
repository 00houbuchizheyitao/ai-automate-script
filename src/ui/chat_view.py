import base64

import flet as ft

from src.agent.agent import Agent


class ChatView(ft.Column):
    def __init__(self, page: ft.Page, agent: Agent):
        # 注意：不要在 __init__ 中直接给 self.controls 赋值，这会覆盖 ft.Column 内部的机制
        super().__init__(expand=True)
        self._page = page
        self.agent = agent

        self._pending_image_bytes: bytes | None = None

        self.chat_list = ft.ListView(
            expand=True,
            spacing=10,
            padding=20,
            auto_scroll=True,
        )

        self.text_input = ft.TextField(
            hint_text="描述你想自动化的任务...",
            expand=True,
            multiline=True,
            min_lines=1,
            max_lines=4,
            on_submit=self._on_submit,
            border_color=ft.Colors.GREY_400,
            focused_border_color=ft.Colors.BLUE,
            text_size=14,
            content_padding=15,
            cursor_color=ft.Colors.BLUE,
            bgcolor=ft.Colors.GREY_100,
            color=ft.Colors.BLACK,
        )

        self.screenshot_btn = ft.IconButton(
            icon=ft.Icons.IMAGE,
            tooltip="添加截图（可选）",
            on_click=self._on_screenshot_upload,
        )

        self.send_btn = ft.IconButton(
            icon=ft.Icons.SEND,
            tooltip="发送",
            on_click=self._on_send,
        )

        self.file_picker = ft.FilePicker()
        self.file_picker.on_result = self._on_file_picked

        self._image_indicator = ft.Container(visible=False)

        self.input_row = ft.Row(
            controls=[
                self.screenshot_btn,
                self._image_indicator,
                self.text_input,
                self.send_btn,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        # 使用 self.controls.extend 而不是直接 self.controls = [...]
        self.controls.extend([
            ft.Container(
                content=self.chat_list,
                expand=True,
                bgcolor=ft.Colors.WHITE,
            ),
            ft.Container(
                content=self.input_row,
                padding=ft.padding.only(left=20, right=20, top=10, bottom=10),
                bgcolor=ft.Colors.GREY_50,
            ),
        ])

    def did_mount(self):
        # 移除在这里添加 FilePicker 的逻辑，避免在页面初始加载时报错
        pass

    def _add_message(self, role: str, content: str, image_bytes: bytes | None = None):
        if role == "user":
            avatar = ft.CircleAvatar(content=ft.Text("U"), bgcolor=ft.Colors.BLUE_100)
        else:
            avatar = ft.CircleAvatar(content=ft.Text("A"), bgcolor=ft.Colors.GREEN_100)

        message_content = []

        if image_bytes:
            image_b64 = base64.b64encode(image_bytes).decode()
            message_content.append(
                ft.Image(
                    src_base64=image_b64,
                    width=300,
                    fit=ft.ImageFit.CONTAIN,
                )
            )

        if content:
            message_content.append(ft.Text(content, selectable=True, color=ft.Colors.BLACK))

        bubble = ft.Container(
            content=ft.Row(
                controls=[
                    avatar,
                    ft.Column(controls=message_content),
                ],
                alignment=ft.MainAxisAlignment.START if role == "user" else ft.MainAxisAlignment.END,
            ),
            padding=10,
        )

        self.chat_list.controls.append(bubble)
        self._page.update()

    def _update_image_indicator(self):
        if self._pending_image_bytes:
            self._image_indicator = ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Icon(ft.Icons.IMAGE, size=16, color=ft.Colors.GREEN),
                        ft.Text("已添加截图", size=12, color=ft.Colors.BLACK),
                        ft.IconButton(
                            icon=ft.Icons.CLOSE,
                            icon_size=14,
                            on_click=self._clear_pending_image,
                            icon_color=ft.Colors.BLACK,
                        ),
                    ],
                    spacing=4,
                ),
                visible=True,
            )
        else:
            self._image_indicator = ft.Container(visible=False)

        self.input_row.controls = [
            self.screenshot_btn,
            self._image_indicator,
            self.text_input,
            self.send_btn,
        ]
        self._page.update()

    def _clear_pending_image(self, e=None):
        self._pending_image_bytes = None
        self.agent._pending_image = None
        self._update_image_indicator()

    async def _on_submit(self, e):
        await self._send_message()

    async def _on_send(self, e):
        await self._send_message()

    async def _send_message(self):
        text = self.text_input.value.strip()
        if not text and not self._pending_image_bytes:
            return

        if self._pending_image_bytes:
            self._add_message("user", text or "（附带截图）", image_bytes=self._pending_image_bytes)
            self.agent.set_pending_image(self._pending_image_bytes)
            self._pending_image_bytes = None
            self._update_image_indicator()
        else:
            self._add_message("user", text)

        self.text_input.value = ""
        self._page.update()

        try:
            response = await self.agent.process(text)
            self._add_message("assistant", response)
        except Exception as e:
            self._add_message("assistant", f"出错了: {str(e)}")
        
        self._page.update()

    def _on_screenshot_upload(self, e):
        # 在用户点击上传按钮时，再将其添加到 overlay 中（仅添加一次）
        if self.file_picker not in self._page.overlay:
            self._page.overlay.append(self.file_picker)
            self._page.update()
        
        self.file_picker.pick_files(
            allowed_extensions=["png", "jpg", "jpeg", "bmp"],
            dialog_title="选择截图（可选）",
        )

    def _on_file_picked(self, e: ft.FilePickerResultEvent):
        if not e.files:
            return

        file = e.files[0]
        with open(file.path, "rb") as f:
            self._pending_image_bytes = f.read()

        self._update_image_indicator()
