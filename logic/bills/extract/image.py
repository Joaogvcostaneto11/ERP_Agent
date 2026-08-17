from __future__ import annotations

import base64
import io

from PIL import Image, ImageOps

from logic.bills.extract.media import UnsupportedMedia

MAX_EDGE = 1568       # the API downsamples past this, so larger is pure cost
MAX_B64_BYTES = 5 * 1024 * 1024
# Checked against the RAW upload, before Image.open — MAX_B64_BYTES measures the
# OUTPUT and so can only fire after a hostile file has already been decoded.
# 25MB clears any real photo of an invoice by a wide margin (the scans in
# bills_examples/ are 75-130KB; a 50MP phone JPEG is ~10-15MB).
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
# A ~30KB PNG can declare ~150M pixels; Pillow only *warns* below 2x its own
# MAX_IMAGE_PIXELS (89,478,485) and decodes it in full, ~450MB of RGB once
# exif_transpose and resize have each taken a copy. Cap the declared pixel count
# from the header instead. 50MP sits above every mainstream phone camera and
# well under Pillow's own threshold.
MAX_PIXELS = 50_000_000
_ORIENTATION_TAG = 0x0112


def prepare(data: bytes, media_type: str) -> tuple[str, str]:
    """Return (media_type, base64) ready for a vision content block.

    Phone photos carry their rotation in EXIF metadata rather than in the
    pixels, so a sideways invoice would reach the model sideways without
    exif_transpose. Re-encoding is skipped entirely when the image needs
    neither rotation nor resizing, so the original bytes and media type
    survive untouched."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise UnsupportedMedia("image file is too large — send a smaller photo")
    try:
        return _decode_and_fit(data, media_type)
    except UnsupportedMedia:
        raise
    except Exception as e:
        # Same contract as ocr.py's OcrUnavailable normalization, for the same
        # reason: Pillow raises heterogeneous, non-OSError types on hostile or
        # malformed input — DecompressionBombError subclasses plain Exception,
        # and a corrupt EXIF block surfaces from getexif() as struct.error or
        # SyntaxError. Anything that escapes prepare() reaches the operator as a
        # 500; normalizing to UnsupportedMedia (a RuntimeError) makes it the
        # 400 the spec calls for.
        raise UnsupportedMedia(f"could not read the image: {e}") from e


def _decode_and_fit(data: bytes, media_type: str) -> tuple[str, str]:
    img = Image.open(io.BytesIO(data))   # lazy: parses the header, no pixels yet
    width, height = img.size
    if width * height > MAX_PIXELS:
        raise UnsupportedMedia(
            f"image is too large to process ({width}x{height} pixels)")
    img.load()

    rotated = img.getexif().get(_ORIENTATION_TAG, 1) not in (0, 1)
    img = ImageOps.exif_transpose(img)

    width, height = img.size
    scale = MAX_EDGE / max(width, height)
    resized = scale < 1
    if resized:
        img = img.resize((max(1, round(width * scale)), max(1, round(height * scale))),
                         Image.LANCZOS)

    if rotated or resized:
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=85)
        data, media_type = buf.getvalue(), "image/jpeg"

    b64 = base64.b64encode(data).decode("ascii")
    if len(b64) > MAX_B64_BYTES:
        raise UnsupportedMedia("image is too large — send a smaller photo")
    return media_type, b64
