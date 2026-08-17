import base64
import io
import struct
import zlib

import pytest
from PIL import Image

from logic.bills.extract import image as image_module
from logic.bills.extract.image import (MAX_EDGE, MAX_PIXELS, MAX_UPLOAD_BYTES,
                                       prepare)
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


def _png_declaring(width: int, height: int) -> bytes:
    """A tiny PNG whose IHDR *claims* width x height. This is the decompression
    bomb shape: ~70 bytes on the wire, hundreds of MB once decoded."""
    data = bytearray(_png_1x1())
    data[16:20] = width.to_bytes(4, "big")    # IHDR width
    data[20:24] = height.to_bytes(4, "big")   # IHDR height
    data[29:33] = zlib.crc32(bytes(data[12:29])).to_bytes(4, "big")
    return bytes(data)


def _png_1x1() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), "white").save(buf, "PNG")
    return buf.getvalue()


def test_prepare_rejects_pixel_bomb_below_pillows_own_threshold():
    # 150M pixels: over MAX_PIXELS but under 2x Image.MAX_IMAGE_PIXELS, where
    # Pillow only warns and decodes in full (~450MB of RGB once exif_transpose
    # and resize have each taken a copy). We must reject it from the header.
    bomb = _png_declaring(20_000, 7_500)
    assert 20_000 * 7_500 > MAX_PIXELS
    assert len(bomb) < 1024
    with pytest.raises(UnsupportedMedia) as exc_info:
        prepare(bomb, "image/png")
    # Only the header check produces this message; if it's skipped, Pillow's
    # img.load() chokes on the corrupt/short IDAT stream and prepare()'s
    # catch-all normalizes that into a different "could not read the image:
    # ..." message instead.
    assert str(exc_info.value) == "image is too large to process (20000x7500 pixels)"


def test_prepare_turns_pillow_decompression_bomb_error_into_unsupported_media():
    # Past 2x Image.MAX_IMAGE_PIXELS Pillow raises DecompressionBombError, which
    # subclasses plain Exception — not OSError — so it used to escape prepare()
    # and app.py's `except RuntimeError`, surfacing as a 500 instead of a 400.
    with pytest.raises(UnsupportedMedia):
        prepare(_png_declaring(30_000, 10_000), "image/png")


def test_prepare_rejects_oversized_upload_before_opening_it(monkeypatch):
    monkeypatch.setattr(image_module, "MAX_UPLOAD_BYTES", 10)

    def _must_not_open(*a, **kw):
        raise AssertionError("the byte ceiling must be checked before Image.open")

    monkeypatch.setattr(image_module.Image, "open", _must_not_open)
    with pytest.raises(UnsupportedMedia) as exc_info:
        prepare(_jpeg((100, 80)), "image/jpeg")
    # Only the byte-ceiling guard produces this message; if it's skipped, the
    # AssertionError from the patched Image.open gets normalized by prepare()'s
    # catch-all into a different "could not read the image: ..." message instead.
    assert str(exc_info.value) == "image file is too large — send a smaller photo"


def test_upload_ceiling_leaves_room_for_a_real_phone_photo():
    # Real scans in bills_examples/ are 75-130KB; a 50MP phone JPEG is ~10-15MB.
    # The ceiling exists to stop bombs, not to reject genuine uploads.
    assert MAX_UPLOAD_BYTES >= 20 * 1024 * 1024


def test_prepare_survives_a_corrupt_exif_block(monkeypatch):
    # getexif() used to sit outside the guarded region entirely; struct.error is
    # not an OSError, so malformed EXIF reached the operator as a 500.
    def _boom(self):
        raise struct.error("bad exif")

    monkeypatch.setattr(image_module.Image.Image, "getexif", _boom)
    with pytest.raises(UnsupportedMedia):
        prepare(_jpeg((100, 80)), "image/jpeg")


def test_prepare_rejects_when_base64_string_length_exceeds_cap(monkeypatch):
    # Pin the intended semantics: MAX_B64_BYTES bounds len(b64), the base64
    # *string* length that actually goes over the wire to the API, not the
    # raw byte count of the image. Monkeypatching the constant down lets a
    # small, untouched image (well under any real limit) trip the cap
    # deterministically, without allocating a genuinely 5MB+ image.
    monkeypatch.setattr(image_module, "MAX_B64_BYTES", 10)
    with pytest.raises(UnsupportedMedia):
        prepare(_jpeg((100, 80)), "image/jpeg")
