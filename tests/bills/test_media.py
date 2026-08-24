import pytest

from logic.bills.extract.media import UnsupportedMedia, sniff

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
WEBP = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"\x00" * 16
GIF = b"GIF89a" + b"\x00" * 16
PDF = b"%PDF-1.7\n" + b"\x00" * 16
# ISO-BMFF/HEIC: the brand lives at offset 4, so nothing matches at offset 0.
HEIC = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 16


@pytest.mark.parametrize("data,expected", [
    (PDF, "application/pdf"),
    (JPEG, "image/jpeg"),
    (PNG, "image/png"),
    (WEBP, "image/webp"),
    (GIF, "image/gif"),
    (b"GIF87a" + b"\x00" * 16, "image/gif"),
])
def test_sniff_detects_accepted_formats(data, expected):
    assert sniff(data) == expected


@pytest.mark.parametrize("data", [HEIC, b"not a file at all", b"", b"RIFFxxxxAVI "])
def test_sniff_rejects_unsupported(data):
    with pytest.raises(UnsupportedMedia):
        sniff(data)


def test_unsupported_media_is_a_runtime_error():
    # app.py maps RuntimeError to HTTP 400; this keeps that mapping working.
    assert issubclass(UnsupportedMedia, RuntimeError)


def test_sniff_ignores_filename_and_trusts_bytes():
    # A PDF renamed to .jpg is still a PDF.
    assert sniff(PDF) == "application/pdf"
