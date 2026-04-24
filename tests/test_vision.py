import pytest

from src.vision.image_processor import ImageProcessor


class TestImageProcessor:
    def test_load_image(self, sample_image_bytes):
        result = ImageProcessor.load_image(sample_image_bytes)
        assert result is not None
        assert len(result.shape) == 3

    def test_resize_image(self, sample_image_bytes):
        resized = ImageProcessor.resize_image(sample_image_bytes, 800, 600)
        assert resized is not None
        assert len(resized) > 0


@pytest.fixture
def sample_image_bytes():
    from PIL import Image
    import io

    img = Image.new("RGB", (100, 100), color="red")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
