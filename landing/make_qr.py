"""Generate landing/qr.png — a QR code that opens Baseline on WhatsApp.

Usage:
    python landing/make_qr.py +14155238886
    python landing/make_qr.py +14155238886 "hi"   # custom prefilled text

The number is your Twilio WhatsApp sender (digits, optional leading +).
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python landing/make_qr.py <whatsapp_number> [prefilled_text]")
        raise SystemExit(1)

    number = sys.argv[1].lstrip("+").replace(" ", "")
    text = sys.argv[2] if len(sys.argv) > 2 else "hi"
    link = f"https://wa.me/{number}?text={text}"

    import qrcode

    img = qrcode.make(link)
    out = Path(__file__).parent / "qr.png"
    img.save(out)
    print(f"Wrote {out}")
    print(f"Encodes: {link}")
    print("Remember to also update the 'Open WhatsApp' button href in index.html.")


if __name__ == "__main__":
    main()
