GUI_AUTOMATION_TEMPLATE = '''"""
GUI 自动化脚本: {task_name}
生成时间: {timestamp}
"""

import pyautogui
import time
import logging
import sys
import cv2
import numpy as np
from mss import mss

pyautogui.PAUSE = 0.5
pyautogui.FAILSAFE = True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def wait_for_image(template_path: str, timeout: int = 10, confidence: float = 0.8):
    """等待指定图像出现在屏幕上"""
    sct = mss()
    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
    if template is None:
        raise FileNotFoundError(f"模板图片未找到: {{template_path}}")

    start_time = time.time()
    while time.time() - start_time < timeout:
        screenshot = sct.grab(sct.monitors[0])
        img = np.array(screenshot)
        img_gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        result = cv2.matchTemplate(img_gray, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val >= confidence:
            h, w = template.shape
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            logger.info(f"找到目标图像，位置: ({{center_x}}, {{center_y}})，置信度: {{max_val:.2f}}")
            return center_x, center_y

        time.sleep(0.5)

    raise TimeoutError(f"等待图像超时: {{template_path}}")


def click_at(x: int, y: int, clicks: int = 1, interval: float = 0.1):
    """在指定位置点击"""
    logger.info(f"点击位置: ({{x}}, {{y}})")
    pyautogui.click(x=x, y=y, clicks=clicks, interval=interval)


def type_text(text: str, interval: float = 0.05):
    """输入文字"""
    logger.info(f"输入文字: {{text[:20]}}...")
    pyautogui.typewrite(text, interval=interval)


def press_key(key: str):
    """按下按键"""
    logger.info(f"按下按键: {{key}}")
    pyautogui.press(key)


def hotkey(*keys):
    """组合键"""
    logger.info(f"组合键: {{'+'.join(keys)}}")
    pyautogui.hotkey(*keys)


def main():
    logger.info("脚本开始执行: {task_name}")
    try:
{script_body}
        logger.info("脚本执行完成")
    except pyautogui.FailSafeException:
        logger.error("触发安全退出")
        sys.exit(1)
    except TimeoutError as e:
        logger.error(f"等待超时: {{e}}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"脚本执行出错: {{e}}")
        sys.exit(1)


if __name__ == "__main__":
    main()
'''
