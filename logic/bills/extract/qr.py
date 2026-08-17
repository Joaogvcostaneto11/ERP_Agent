from __future__ import annotations

import io


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
    """
    try:
        import cv2
        import numpy as np
        from PIL import Image, ImageOps
    except ImportError:
        return None

    try:
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("L")
        detector = cv2.QRCodeDetector()
        for scale in (1, 2):
            arr = np.array(img if scale == 1 else img.resize(
                (img.width * scale, img.height * scale), Image.LANCZOS))
            payload, _, _ = detector.detectAndDecode(arr)
            if payload:
                return payload
    except Exception:
        # Any decoder or image failure means "no QR", never a broken upload.
        return None
    return None
