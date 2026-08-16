import base64
import io

import pytest
from PIL import Image

from logic.bills.extract.image import MAX_EDGE, prepare
from logic.bills.extract.media import UnsupportedMedia


def _jpeg(size, orientation=None) -> bytes:
    img = Image.new("RGB", size, "white")
    buf = io.BytesIO()
    if orientation is None:
        img.save(buf, "JPEG")
    else:
        exif = img.getexif()
        exif[0x0112] = orientation  # EXIF Orientation tag
        img.save(buf, "JPEG", exif=exif)
    return buf.getvalue()


def _decode(b64: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(b64)))


def test_prepare_applies_exif_rotation():
    # Orientation 6 means "rotate 90 CW to display": a 40x20 landscape photo is
    # really a 20x40 portrait. Claude sees pixels, not metadata, so we must bake
    # the rotation in.
    media_type, b64 = prepare(_jpeg((40, 20), orientation=6), "image/jpeg")
    assert _decode(b64).size == (20, 40)
    assert media_type == "image/jpeg"


def test_prepare_downscales_long_edge():
    _, b64 = prepare(_jpeg((3000, 1500)), "image/jpeg")
    assert _decode(b64).size == (MAX_EDGE, MAX_EDGE // 2)


def test_prepare_passes_small_unrotated_image_through_untouched():
    data = _jpeg((100, 80))
    media_type, b64 = prepare(data, "image/jpeg")
    assert base64.b64decode(b64) == data
    assert media_type == "image/jpeg"


def test_prepare_preserves_media_type_when_untouched():
    img = Image.new("RGB", (50, 50), "white")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    media_type, _ = prepare(buf.getvalue(), "image/png")
    assert media_type == "image/png"


def test_prepare_reencodes_resized_png_as_jpeg():
    img = Image.new("RGB", (2000, 1000), "white")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    media_type, b64 = prepare(buf.getvalue(), "image/png")
    assert media_type == "image/jpeg"
    assert _decode(b64).size == (MAX_EDGE, MAX_EDGE // 2)


def test_prepare_rejects_undecodable_bytes():
    with pytest.raises(UnsupportedMedia):
        prepare(b"\xff\xd8\xff not really a jpeg", "image/jpeg")
