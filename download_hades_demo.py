"""Download a profile's source lecture video into video/<profile>.mp4.

Usage:  python download_hades_demo.py [profile]     (default: hades_demo)
URL comes from config.YOUTUBE_URLS — no second copy of the link (plan G4/G5).
"""
import os
import subprocess
import sys

import config

profile = sys.argv[1] if len(sys.argv) > 1 else "hades_demo"
url = config.YOUTUBE_URLS.get(profile)
if not url:
    sys.exit(f"No YouTube URL configured for profile {profile!r} (see config.YOUTUBE_URLS)")

os.makedirs(config.VIDEO_DIR, exist_ok=True)
out = os.path.join(config.VIDEO_DIR, f"{profile}.%(ext)s")
# 720p keeps size ~1.2GB vs 1080p ~2.5GB, faster whisper, judges don't need 4K
cmd = [
    sys.executable, "-m", "yt_dlp",
    url,
    "-o", out,
    "-f", "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/bv*+ba/b",
    "--merge-output-format", "mp4",
    "--no-playlist",
    "--progress",
]
print("Running:", " ".join(cmd))
r = subprocess.call(cmd)
sys.exit(r)
