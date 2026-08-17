import io
import zlib
from pathlib import Path

import pytest
from PIL import Image, ImageOps

from logic.bills.extract.image import MAX_PIXELS
from logic.bills.extract.qr import UPSCALE_MAX_PIXELS, decode

EXAMPLES = Path(__file__).resolve().parents[2] / "bills_examples"

# bills_examples/ is untracked; these tests skip rather than fail where it is absent.
pytestmark = pytest.mark.skipif(not EXAMPLES.is_dir(),
                                reason="bills_examples/ not present")


def _png_1x1() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), "white").save(buf, "PNG")
    return buf.getvalue()


def _png_declaring(width: int, height: int) -> bytes:
    """A tiny PNG whose IHDR *claims* width x height — same decompression-bomb
    shape as tests/bills/test_image.py: ~70 bytes on the wire, a huge declared
    pixel count."""
    data = bytearray(_png_1x1())
    data[16:20] = width.to_bytes(4, "big")    # IHDR width
    data[20:24] = height.to_bytes(4, "big")   # IHDR height
    data[29:33] = zlib.crc32(bytes(data[12:29])).to_bytes(4, "big")
    return bytes(data)


def test_decode_returns_none_for_non_image_bytes():
    assert decode(b"not an image at all") is None


def test_decode_returns_none_when_the_decoder_is_not_installed(monkeypatch):
    # Global constraint: a missing decoder must degrade to "no QR", never break
    # an upload. Simulate the library being absent.
    import builtins
    real_import = builtins.__import__

    def _no_decoder(name, *args, **kwargs):
        if name in ("cv2", "pyzbar", "pyzbar.pyzbar"):
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_decoder)
    assert decode((EXAMPLES / "scanner_forumsi_1.jpeg").read_bytes()) is None


def test_decode_returns_none_for_a_pixel_bomb_without_decoding(monkeypatch):
    # 20000x7500 = 150M declared pixels: over MAX_PIXELS, in ~70 bytes on the
    # wire. The hard ceiling must reject this from the lazy header, before any
    # pixel decode runs. decode() swallows every exception itself, so a
    # patched exif_transpose that *raises* would still leave the outer
    # `decode(bomb) is None` assertion passing whether or not the guard ran —
    # the failure would just come from decode()'s own catch-all instead of
    # the ceiling. Track the call instead, and assert on that.
    calls = []
    real_exif_transpose = ImageOps.exif_transpose

    def _tracking(*a, **kw):
        calls.append(1)
        return real_exif_transpose(*a, **kw)

    monkeypatch.setattr(ImageOps, "exif_transpose", _tracking)
    bomb = _png_declaring(20_000, 7_500)
    assert 20_000 * 7_500 > MAX_PIXELS
    assert decode(bomb) is None
    assert calls == [], "the pixel ceiling must be checked before decoding"


def test_decode_skips_the_upscale_tier_for_a_large_image(monkeypatch):
    # A width x height over UPSCALE_MAX_PIXELS but under MAX_PIXELS is a
    # legitimate upload (e.g. a high-resolution phone photo): it should still
    # get the cheap scale=1 attempt, but never pay for the 2x resize. Track
    # the resize call rather than raising from the patch, for the same reason
    # as the pixel-bomb test above — decode()'s catch-all would swallow a
    # raised exception either way.
    width, height = 4000, 3200
    assert UPSCALE_MAX_PIXELS < width * height <= MAX_PIXELS

    calls = []
    real_resize = Image.Image.resize

    def _tracking(self, *a, **kw):
        calls.append(1)
        return real_resize(self, *a, **kw)

    monkeypatch.setattr(Image.Image, "resize", _tracking)
    buf = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buf, "JPEG")
    assert decode(buf.getvalue()) is None
    assert calls == [], "scale=2 must be skipped above UPSCALE_MAX_PIXELS"


def test_decode_returns_none_for_an_invoice_without_a_qr():
    # scanner_forumsi_4 is a Spanish supplier's invoice and carries no AT QR.
    assert decode((EXAMPLES / "scanner_forumsi_4.jpeg").read_bytes()) is None


@pytest.mark.parametrize("name", [
    "scanner_forumsi_1.jpeg", "scanner_forumsi_2.jpeg",
    pytest.param("scanner_forumsi_3.jpeg", marks=pytest.mark.xfail(
        reason="QR too small to decode at 1080x1920", strict=True)),
    "scanner_forumsi_5.jpeg", "scanner_forumsi_6.jpeg",
])
def test_decode_reads_the_at_payload(name):
    payload = decode((EXAMPLES / name).read_bytes())
    assert payload is not None, f"no QR decoded from {name}"
    assert payload.startswith("A:")
    assert "*O:" in payload
