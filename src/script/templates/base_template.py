BASE_TEMPLATE = '''"""
{description}
生成时间: {timestamp}
目标分辨率: {resolution}
"""

import pyautogui
import time
import logging
import sys

pyautogui.PAUSE = {pause_interval}
pyautogui.FAILSAFE = True

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    logger.info("脚本开始执行")
    try:
{script_body}
        logger.info("脚本执行完成")
    except pyautogui.FailSafeException:
        logger.error("触发安全退出（鼠标移至屏幕角落）")
        sys.exit(1)
    except Exception as e:
        logger.error(f"脚本执行出错: {{e}}")
        sys.exit(1)


if __name__ == "__main__":
    main()
'''
