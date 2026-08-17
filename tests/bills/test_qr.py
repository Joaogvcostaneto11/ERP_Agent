from pathlib import Path

import pytest

from logic.bills.extract.qr import decode

EXAMPLES = Path(__file__).resolve().parents[2] / "bills_examples"

# bills_examples/ is untracked; these tests skip rather than fail where it is absent.
pytestmark = pytest.mark.skipif(not EXAMPLES.is_dir(),
                                reason="bills_examples/ not present")


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
