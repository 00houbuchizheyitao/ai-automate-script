import io

import cv2
import numpy as np
from PIL import Image


class ImageProcessor:
    @staticmethod
    def load_image(image_bytes: bytes) -> np.ndarray:
        image = Image.open(io.BytesIO(image_bytes))
        return np.array(image)

    @staticmethod
    def find_template(source_bytes: bytes, template_bytes: bytes, threshold: float = 0.8) -> dict | None:
        source = ImageProcessor.load_image(source_bytes)
        template = ImageProcessor.load_image(template_bytes)

        source_gray = cv2.cvtColor(source, cv2.COLOR_RGB2GRAY)
        template_gray = cv2.cvtColor(template, cv2.COLOR_RGB2GRAY)

        result = cv2.matchTemplate(source_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            h, w = template_gray.shape
            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            return {
                "found": True,
                "confidence": float(max_val),
                "position": {"x": int(center_x), "y": int(center_y)},
                "region": {
                    "left": int(max_loc[0]),
                    "top": int(max_loc[1]),
                    "width": int(w),
                    "height": int(h),
                },
            }
        return {"found": False, "confidence": float(max_val)}

    @staticmethod
    def find_all_templates(source_bytes: bytes, template_bytes: bytes, threshold: float = 0.8) -> list[dict]:
        source = ImageProcessor.load_image(source_bytes)
        template = ImageProcessor.load_image(template_bytes)

        source_gray = cv2.cvtColor(source, cv2.COLOR_RGB2GRAY)
        template_gray = cv2.cvtColor(template, cv2.COLOR_RGB2GRAY)

        result = cv2.matchTemplate(source_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        h, w = template_gray.shape

        locations = np.where(result >= threshold)
        matches = []
        for pt in zip(*locations[::-1]):
            center_x = pt[0] + w // 2
            center_y = pt[1] + h // 2
            matches.append(
                {
                    "confidence": float(result[pt[1], pt[0]]),
                    "position": {"x": int(center_x), "y": int(center_y)},
                }
            )
        return matches

    @staticmethod
    def resize_image(image_bytes: bytes, width: int, height: int) -> bytes:
        image = ImageProcessor.load_image(image_bytes)
        resized = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
        pil_image = Image.fromarray(resized)
        buffer = io.BytesIO()
        pil_image.save(buffer, format="PNG")
        return buffer.getvalue()
