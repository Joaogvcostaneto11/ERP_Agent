from __future__ import annotations

import base64
import io

from PIL import Image, ImageOps, UnidentifiedImageError

from logic.bills.extract.media import UnsupportedMedia

MAX_EDGE = 1568       # the API downsamples past this, so larger is pure cost
MAX_B64_BYTES = 5 * 1024 * 1024
_ORIENTATION_TAG = 0x0112


def prepare(data: bytes, media_type: str) -> tuple[str, str]:
    """Return (media_type, base64) ready for a vision content block.

    Phone photos carry their rotation in EXIF metadata rather than in the
    pixels, so a sideways invoice would reach the model sideways without
    exif_transpose. Re-encoding is skipped entirely when the image needs
    neither rotation nor resizing, so the original bytes and media type
    survive untouched."""
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as e:
        raise UnsupportedMedia(f"could not read the image: {e}") from e

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
