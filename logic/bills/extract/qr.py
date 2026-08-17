from __future__ import annotations

import io

from logic.bills.extract.image import MAX_PIXELS

# Above this pixel count, the 2x upscale tier is skipped. A source image this
# large already has ample pixels per QR module, so upscaling buys nothing.
# Chosen so the worst case (4x area at scale=2) never exceeds MAX_PIXELS
# itself — the same ceiling this pipeline already accepts elsewhere
# (image.py). It still covers a modern phone's default photo with headroom
# (a default iPhone photo is 4032x3024 = ~12.2MP); only shots already near
# the 50MP ceiling skip the upscale.
UPSCALE_MAX_PIXELS = MAX_PIXELS // 4


def decode(data: bytes) -> str | None:
    """Return the AT QR payload found in an image, or None.

    Absence of a readable QR is the normal case, not a failure: many suppliers
    are foreign and print none. This never raises — a QR can only ever improve
    the extraction, never block it.

    Runs on the ORIGINAL bytes. `image.prepare` downscales to a 1568px long edge,
    which at observed invoice resolutions drops the QR below the roughly two
    pixels per module a decoder needs.

    Imports are function-local so the module loads where the decoder is absent.

    Uses opencv-python-headless (not pyzbar): a spike found pyzbar's bundled
    libzbar-64.dll fails to import on this environment (missing libiconv.dll
    dependency), while OpenCV achieved full recall on its own as a pure pip
    wheel with no native packaging risk. Scales are (1, 2) only — the spike
    found 4x upscaling added zero additional decodes over 2x at roughly
    3.5-4x the runtime, which is not worth paying on every upload.

    A legitimate 50MP upload (image.py's own ceiling) can cost ~450MB of
    buffers here without a guard: the RGB decode, the grayscale copy, the 2x
    resize (4x area), and the numpy copy of that resize all stack up. Two
    guards bound that: a hard pixel ceiling (reusing MAX_PIXELS, checked from
    the lazy header before any pixel decode) rejects anything decode() itself
    should never need to touch, and the upscale tier is skipped for images
    already well-resourced enough not to need it.
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image, ImageOps
    except ImportError:
        return None

    try:
        img = Image.open(io.BytesIO(data))  # lazy: header only, no pixel decode yet
        width, height = img.size
        if width * height > MAX_PIXELS:
            return None

        img = ImageOps.exif_transpose(img).convert("L")
        detector = cv2.QRCodeDetector()
        scales = (1, 2) if width * height <= UPSCALE_MAX_PIXELS else (1,)
        for scale in scales:
            arr = np.array(img if scale == 1 else img.resize(
                (img.width * scale, img.height * scale), Image.LANCZOS))
            payload, _, _ = detector.detectAndDecode(arr)
            if payload:
                return payload
    except Exception:
        # Any decoder or image failure means "no QR", never a broken upload.
        return None
    return None
