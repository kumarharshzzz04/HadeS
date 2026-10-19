# process_video.py — video → mp3 using config.py paths
# Drop .mp4/.mkv/.mov/.webm into video/ then run: python process_video.py
import os, subprocess, sys
import config

os.makedirs(config.VIDEO_DIR, exist_ok=True)
os.makedirs(config.AUDIO_DIR, exist_ok=True)

if not os.path.exists(config.VIDEO_DIR):
    print(f"Video folder not found: {config.VIDEO_DIR}")
    sys.exit(0)

files = [f for f in os.listdir(config.VIDEO_DIR) if f.lower().endswith((".mp4",".mkv",".mov",".avi",".webm",".m4a"))]
if not files:
    print(f"No video files in {config.VIDEO_DIR} — nothing to do.")
    print("(Your existing transcripts/chunks are kept as-is, no re-process needed.)")
    sys.exit(0)

for file in files:
    input_path  = os.path.join(config.VIDEO_DIR, file)
    output_file = os.path.splitext(file)[0] + ".mp3"
    output_path = os.path.join(config.AUDIO_DIR, output_file)
    if os.path.exists(output_path):
        print(f"Skipping {file} — {output_file} already exists.")
        continue
    print(f"Extracting audio: {file} → {output_file}")
    subprocess.run(["ffmpeg","-y","-i", input_path, "-ab","64k","-map","a", output_path], check=False)
print("Done. Next: python transcribe_parts.py")
