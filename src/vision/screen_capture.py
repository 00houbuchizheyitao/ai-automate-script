import mss
import mss.tools


class ScreenCapture:
    def __init__(self):
        self._sct: mss.mss.base.MSSBase | None = None

    @property
    def sct(self):
        if self._sct is None:
            self._sct = mss.mss()
        return self._sct

    def capture_full(self) -> bytes:
        monitor = self.sct.monitors[0]
        screenshot = self.sct.grab(monitor)
        return mss.tools.to_png(screenshot.rgb, screenshot.size)

    def capture_region(self, left: int, top: int, width: int, height: int) -> bytes:
        monitor = {"left": left, "top": top, "width": width, "height": height}
        screenshot = self.sct.grab(monitor)
        return mss.tools.to_png(screenshot.rgb, screenshot.size)

    def capture_monitor(self, monitor_index: int = 1) -> bytes:
        monitor = self.sct.monitors[monitor_index]
        screenshot = self.sct.grab(monitor)
        return mss.tools.to_png(screenshot.rgb, screenshot.size)

    def get_monitor_info(self) -> list[dict]:
        return [
            {"left": m["left"], "top": m["top"], "width": m["width"], "height": m["height"]}
            for m in self.sct.monitors
        ]

    def close(self):
        if self._sct:
            self._sct.close()
            self._sct = None
