"""Render the HadeS 7th-Convocation creative — PNG image + single-page PDF.

Source of truth is `hades_convocation.html`: a fixed 1240×2480 frame (4:8
portrait, 1:2) carrying the Maharishi University convocation header, the HadeS
project body, the scan panel and the team footer. This script drives headless
Chrome at that exact frame and writes:

    hades_convocation.png    hades_convocation.pdf

The PNG is the shareable image (exported at 2x, so 2480×4960, with the print
resolution stamped into the file); the PDF is the single-sheet version. Page
count is asserted, because a creative that spills onto a second page is a
silent, annoying failure.

The scan panel holds its QR slot open with a placeholder until a code is
supplied. Pass the link the panel should send people to — either a URL (the QR
is generated here, with segno) or an already-made QR image:

    python render_convocation.py --qr https://youtu.be/XXXXXXXX   # demo video
    python render_convocation.py --qr C:/path/to/qr.png           # an export

A video-ish link (YouTube/Vimeo/Drive/Loom) labels the panel PROJECT VIDEO /
"Scan to see the video"; anything else is PROJECT LINK / "Scan to open the
project". After rendering, the QR is decoded back out of the finished sheet so a
poster that doesn't scan cannot slip through.

Usage:
    python render_convocation.py              # PNG + PDF, QR slot left empty
    python render_convocation.py png          # only the PNG
    python render_convocation.py pdf          # only the PDF
    python render_convocation.py --qr <url|path>
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys

DIRECTORY = pathlib.Path(__file__).resolve().parent
SOURCE = DIRECTORY / "hades_convocation.html"
QR_ASSET = DIRECTORY / "assets" / "qr.png"

VIDEO_HOSTS = ("youtu.be", "youtube.com", "vimeo.com", "drive.google.com", "loom.com", "streamable.com")

# exact frame the creative is authored at — 4:8 portrait (1:2)
WIDTH, HEIGHT = 1240, 2480
SCALE = 2  # → 2480×4960

FORMATS = ("png", "pdf")

CHROME_CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)

BASE_FLAGS = (
    "--headless=new",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    "--allow-file-access-from-files",
    "--virtual-time-budget=4000",
)


def find_browser() -> str:
    for name in ("chrome", "google-chrome", "chromium", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in CHROME_CANDIDATES:
        if pathlib.Path(candidate).exists():
            return candidate
    raise SystemExit("No Chrome/Edge/Chromium binary found — cannot rasterise the creative.")


def is_video_link(link: str) -> bool:
    return any(host in link.lower() for host in VIDEO_HOSTS)


def make_qr(spec: str | None) -> str:
    """Write assets/qr.png from a URL (via segno) or from an image file.

    Returns the caption the panel should use: "video" or "link".
    """
    link = (spec or "").strip()
    if not link:
        raise SystemExit("--qr needs the link your poster should point at")

    if not link.startswith(("http://", "https://")):
        given = pathlib.Path(link)
        if not given.exists():
            raise SystemExit(f"--qr expects a URL or an existing image file, got: {link}")
        QR_ASSET.parent.mkdir(parents=True, exist_ok=True)
        QR_ASSET.write_bytes(given.read_bytes())
        print(f"qr        from image {given.name} -> {QR_ASSET.name}")
        return "link"

    try:
        import segno
    except ImportError:
        raise SystemExit(
            "generating a QR needs segno — `pip install segno` (pure python, no deps), "
            "or pass an existing QR image: --qr path/to/qr.png"
        )

    # error correction H survives a smudged or slightly glossy print
    code = segno.make(link, error="h")
    QR_ASSET.parent.mkdir(parents=True, exist_ok=True)
    code.save(QR_ASSET, kind="png", scale=12, border=2)
    print(f"qr        {len(link)} chars -> {QR_ASSET.name}  ({code.designator})")
    return "video" if is_video_link(link) else "link"


def read_qr(png: pathlib.Path) -> str:
    """Decode the QR back out of the finished sheet, so a poster that does not
    scan cannot slip through. Returns "" when no decoder is available."""
    try:
        import cv2
        import numpy as np
        from PIL import Image
    except ImportError:
        return ""

    with Image.open(png) as im:
        page = np.array(im.convert("L"))
    detector = cv2.QRCodeDetector()
    # try the whole sheet, then the bottom half where the panel sits
    for candidate in (page, page[page.shape[0] // 2 :, :]):
        text, _, _ = detector.detectAndDecode(candidate)
        if text:
            return text
    return ""


def page_url(target: str, with_qr: bool) -> str:
    """The panel is opt-in: no QR supplied means no panel on the sheet."""
    return SOURCE.as_uri() + f"?target={target}" + ("&qr=1" if with_qr else "")


DPI = 300  # stamped into the PNG so layout tools know the print resolution


def stamp_dpi(out: pathlib.Path) -> None:
    """Write the print resolution into the PNG.

    Chrome's screenshot carries no dpi metadata, so a 2480x3508 file would be
    treated as 72 dpi and land on a print dialog as a 87x123 cm sheet. Stamping
    300 dpi makes the file actually be A4 in any layout tool. The re-encode is
    lossless, so the pixels are untouched.
    """
    from PIL import Image

    with Image.open(out) as im:
        if im.size != (WIDTH * SCALE, HEIGHT * SCALE):
            raise SystemExit(f"{out.name} came out {im.size}, expected {WIDTH * SCALE}x{HEIGHT * SCALE}")
        im.save(out, dpi=(DPI, DPI), optimize=True)
    with Image.open(out) as im:
        got = im.info.get("dpi")
    if not got or round(float(got[0])) != DPI:
        raise SystemExit(f"{out.name} dpi stamp did not take: {got}")


def render_png(browser: str, target: str, with_qr: bool) -> pathlib.Path:
    out = DIRECTORY / "hades_convocation.png"
    cmd = [
        browser,
        *BASE_FLAGS,
        "--hide-scrollbars",
        f"--force-device-scale-factor={SCALE}",
        f"--window-size={WIDTH},{HEIGHT}",
        f"--screenshot={out}",
        page_url(target, with_qr),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not out.exists() or out.stat().st_size == 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit("Chrome produced no screenshot for the creative")
    stamp_dpi(out)
    return out


def pdf_pages(pdf: pathlib.Path) -> int:
    """Page count, preferring pypdf and falling back to a raw /Count scan."""
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(pdf)).pages)
    except ImportError:
        raw = pdf.read_bytes()
        counts = [int(n) for n in re.findall(rb"/Count\s+(\d+)", raw)]
        return max(counts) if counts else 0


def render_pdf(browser: str, target: str, with_qr: bool) -> pathlib.Path:
    out = DIRECTORY / "hades_convocation.pdf"
    cmd = [
        browser,
        *BASE_FLAGS,
        "--no-pdf-header-footer",
        f"--print-to-pdf={out}",
        page_url(target, with_qr),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not out.exists() or out.stat().st_size == 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit("Chrome produced no PDF for the creative")

    pages = pdf_pages(out)
    if pages != 1:
        raise SystemExit(
            f"{out.name} came out as {pages} pages — the print stylesheet "
            f"(@page size {WIDTH}px {HEIGHT}px) is not holding the creative to one sheet."
        )
    return out


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"missing source: {SOURCE}")

    argv = list(sys.argv[1:])
    qr_spec = None
    if "--qr" in argv:
        i = argv.index("--qr")
        if i + 1 >= len(argv):
            raise SystemExit("--qr needs a URL or an image path after it")
        qr_spec = argv[i + 1]
        del argv[i : i + 2]

    args = [a.lower() for a in argv]
    formats = tuple(a for a in args if a in FORMATS) or FORMATS
    unknown = [a for a in args if a not in FORMATS]
    if unknown:
        raise SystemExit(f"unknown arg(s): {', '.join(unknown)} (formats: {', '.join(FORMATS)})")

    # the scan panel only goes on the sheet when a QR is supplied
    # the sheet is being made for a demo video, so that is the wording the empty
    # slot advertises until a link is supplied
    with_qr = qr_spec is not None
    target = make_qr(qr_spec) if with_qr else "video"
    print(f"panel     {'slot held open (no QR supplied yet)' if not with_qr else target}")

    browser = find_browser()
    print(f"browser   {browser}")
    if "png" in formats:
        out = render_png(browser, target, with_qr)
        print(            f"png -> {out.name}  ({WIDTH * SCALE}x{HEIGHT * SCALE} @ {DPI} dpi, "
            f"{WIDTH * SCALE / DPI:.2f}x{HEIGHT * SCALE / DPI:.2f} in, {out.stat().st_size / 1024:.0f} KB)")
        if with_qr:
            scanned = read_qr(out)
            if scanned:
                print(f"qr scan  decodes to {scanned!r}")
            else:
                print("qr scan  decoder found no QR to verify — check the panel by eye")
    if "pdf" in formats:
        out = render_pdf(browser, target, with_qr)
        print(f"pdf -> {out.name}  ({pdf_pages(out)} page, {out.stat().st_size / 1024:.0f} KB)")
    print("RENDER_READY")


if __name__ == "__main__":
    main()
