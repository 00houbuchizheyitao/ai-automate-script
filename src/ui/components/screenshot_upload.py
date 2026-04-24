import flet as ft


class ScreenshotUpload(ft.Container):
    def __init__(self, on_image_selected):
        self.on_image_selected = on_image_selected
        self.file_picker = ft.FilePicker(on_result=self._on_result)

        self.upload_area = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Icon(ft.Icons.ADD_PHOTO_ALTERNATE, size=40, color=ft.Colors.GREY_400),
                    ft.Text("点击或拖拽上传截图", color=ft.Colors.GREY_500),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
            ),
            width=200,
            height=150,
            border=ft.border.all(2, ft.Colors.GREY_300),
            border_radius=8,
            on_click=self._on_click,
        )

        super().__init__(content=self.upload_area)

    def _on_click(self, e):
        self.file_picker.pick_files(
            allowed_extensions=["png", "jpg", "jpeg", "bmp"],
            dialog_title="选择截图",
        )

    def _on_result(self, e: ft.FilePickerResultEvent):
        if e.files:
            self.on_image_selected(e.files[0].path)
