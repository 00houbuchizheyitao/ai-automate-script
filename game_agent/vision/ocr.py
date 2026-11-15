import io

import easyocr


class OCRProcessor:
    def __init__(self, languages: list[str] | None = None, gpu: bool = False):
        self.languages = languages or ["ch_sim", "en"]
        self.gpu = gpu
        self._reader: easyocr.Reader | None = None

    @property
    def reader(self) -> easyocr.Reader:
        if self._reader is None:
            self._reader = easyocr.Reader(self.languages, gpu=self.gpu)
        return self._reader

    def extract_text(self, image_bytes: bytes) -> str:
        import numpy as np
        from PIL import Image

        image = Image.open(io.BytesIO(image_bytes))
        image_np = np.array(image)

        results = self.reader.readtext(image_np)
        text_parts = [detection[1] for detection in results if detection[2] > 0.3]
        return "\n".join(text_parts)

    def extract_text_with_positions(self, image_bytes: bytes) -> list[dict]:
        import numpy as np
        from PIL import Image

        image = Image.open(io.BytesIO(image_bytes))
        image_np = np.array(image)

        results = self.reader.readtext(image_np)
        extracted = []
        for bbox, text, confidence in results:
            if confidence > 0.3:
                x_center = (bbox[0][0] + bbox[2][0]) / 2
                y_center = (bbox[0][1] + bbox[2][1]) / 2
                extracted.append(
                    {
                        "text": text,
                        "confidence": confidence,
                        "position": {
                            "x": int(x_center),
                            "y": int(y_center),
                            "bbox": [[int(p[0]), int(p[1])] for p in bbox],
                        },
                    }
                )
        return extracted
