"""Render the 9:16 HadeS poster in both themes — PNG image + single-page PDF.

Source of truth is `hades_poster.html` (one file, two themes via ?theme=dark|light).
This script drives headless Chrome at the exact poster frame and writes:

    hades_poster_dark.png    hades_poster_dark.pdf
    hades_poster_light.png   hades_poster_light.pdf

The PNG is the shareable image; the PDF is the single-sheet version for
printing or sending. Page count is asserted, because a poster that spills
onto a second page is a silent, annoying failure.

Usage:
    python render_poster.py            # both themes, both formats
    python render_poster.py dark       # one theme
    python render_poster.py dark pdf   # only the PDF
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys

DIRECTORY = pathlib.Path(__file__).resolve().parent
SOURCE = DIRECTORY / "hades_poster.html"

# exact 9:16 frame, 1x — the poster CSS is authored at this size
WIDTH, HEIGHT = 1080, 1920
SCALE = 2  # retina export

THEMES = ("dark", "light")
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
    raise SystemExit("No Chrome/Edge/Chromium binary found — cannot rasterise the poster.")


def source_url(theme: str) -> str:
    return SOURCE.as_uri() + f"?theme={theme}"


def render_png(browser: str, theme: str) -> pathlib.Path:
    out = DIRECTORY / f"hades_poster_{theme}.png"
    cmd = [
        browser,
        *BASE_FLAGS,
        "--hide-scrollbars",
        f"--force-device-scale-factor={SCALE}",
        f"--window-size={WIDTH},{HEIGHT}",
        f"--screenshot={out}",
        source_url(theme),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not out.exists() or out.stat().st_size == 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit(f"Chrome produced no screenshot for theme={theme}")
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


def render_pdf(browser: str, theme: str) -> pathlib.Path:
    out = DIRECTORY / f"hades_poster_{theme}.pdf"
    cmd = [
        browser,
        *BASE_FLAGS,
        "--no-pdf-header-footer",
        f"--print-to-pdf={out}",
        source_url(theme),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if not out.exists() or out.stat().st_size == 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit(f"Chrome produced no PDF for theme={theme}")

    pages = pdf_pages(out)
    if pages != 1:
        raise SystemExit(
            f"{out.name} came out as {pages} pages — the print stylesheet "
            f"(@page size {WIDTH}px {HEIGHT}px) is not holding the poster to one sheet."
        )
    return out


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"missing source: {SOURCE}")

    args = [a.lower() for a in sys.argv[1:]]
    themes = tuple(a for a in args if a in THEMES) or THEMES
    formats = tuple(a for a in args if a in FORMATS) or FORMATS
    unknown = [a for a in args if a not in THEMES and a not in FORMATS]
    if unknown:
        raise SystemExit(
            f"unknown arg(s): {', '.join(unknown)} (themes: {', '.join(THEMES)}; formats: {', '.join(FORMATS)})"
        )

    browser = find_browser()
    print(f"browser   {browser}")
    for theme in themes:
        if "png" in formats:
            out = render_png(browser, theme)
            print(f"{theme:<6} png -> {out.name}  ({out.stat().st_size / 1024:.0f} KB)")
        if "pdf" in formats:
            out = render_pdf(browser, theme)
            print(f"{theme:<6} pdf -> {out.name}  ({pdf_pages(out)} page, {out.stat().st_size / 1024:.0f} KB)")
    print("RENDER_READY")


if __name__ == "__main__":
    main()
