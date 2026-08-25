from __future__ import annotations

ACCEPTED = "PDF, JPEG, PNG, WebP or GIF"

# Ceiling on the RAW upload, applied to every accepted type before anything
# parses it. 25MB clears any real invoice by a wide margin (the scans in
# bills_examples/ are 75-130KB; a 50MP phone JPEG is ~10-15MB). It lives here
# rather than in one extractor because both branches need the same answer --
# when only image.py enforced it, PDFs reached poppler unbounded.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class UnsupportedMedia(RuntimeError):
    """The uploaded bytes are not a file type we can extract from."""


def sniff(data: bytes) -> str:
    """Identify the upload by magic bytes. Filenames and client-supplied
    Content-Type headers are user-controlled and routinely wrong coming from a
    phone upload chain, so neither is consulted."""
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    raise UnsupportedMedia(f"unsupported file type — upload a {ACCEPTED} file")
