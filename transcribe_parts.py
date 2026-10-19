# transcribe_parts.py — audio → text with real timestamps (faster-whisper), profile-aware
# Auto GPU->CPU fallback. Respects KMP_DUPLICATE_LIB_OK.
import os, json, sys, argparse
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
# Windows Python 3.8+: add NVIDIA DLL dirs so ctranslate2 finds cublas/cudnn at encode time.
# Found from the interpreter that is actually running (G1): the old list hardcoded one machine's
# anaconda path, and since it is os.path.exists-guarded it silently no-opped elsewhere — GPU
# transcribe quietly fell back to CPU. Same effect, no machine literal.
def _nvidia_dll_dirs():
    import importlib.util
    try:
        spec = importlib.util.find_spec("nvidia")  # namespace pkg from the nvidia-*-cu12 wheels
        roots = list(spec.submodule_search_locations or []) if spec else []
    except Exception:  # noqa: BLE001
        roots = []
    return [
        os.path.join(root, lib, "bin")
        for root in roots
        for lib in ("cublas", "cudnn", "cuda_nvrtc", "cuda_runtime")
    ]

for _dll_dir in _nvidia_dll_dirs():
    if os.path.exists(_dll_dir):
        try: os.add_dll_directory(_dll_dir)
        except Exception: pass
        os.environ["PATH"] = _dll_dir + os.pathsep + os.environ.get("PATH", "")
import config

parser = argparse.ArgumentParser()
parser.add_argument("--profile", default="og", choices=config.AVAILABLE_PROFILES)
args = parser.parse_args()
paths = config.profile_paths(args.profile)

try:
    from faster_whisper import WhisperModel
except ImportError:
    print("Missing faster-whisper. Run: pip install faster-whisper")
    sys.exit(1)

os.makedirs(paths["TRANSCRIPTS_DIR"], exist_ok=True)

src_dir = config.AUDIO_DIR if os.path.exists(config.AUDIO_DIR) and any(
    f.lower().endswith((".mp3",".m4a",".wav",".flac",".mp4",".mkv")) for f in os.listdir(config.AUDIO_DIR)
) else config.VIDEO_DIR if os.path.exists(config.VIDEO_DIR) else config.AUDIO_DIR

if not os.path.exists(src_dir):
    print(f"Source folder not found: {src_dir}")
    sys.exit(0)

files = sorted(f for f in os.listdir(src_dir) if f.lower().endswith((".mp3",".m4a",".wav",".flac",".mp4",".mkv",".mov",".avi",".webm")))
if not files:
    print(f"No audio/video files in {src_dir} — nothing to transcribe.")
    print(f"Tip: drop the 3-4h .mp4 into {config.VIDEO_DIR} then: python process_video.py  ->  python transcribe_parts.py --profile {args.profile}")
    sys.exit(0)

print(f"Profile: {args.profile}  ->  {paths['TRANSCRIPTS_DIR']}")
print(f"Source:  {src_dir}  ({len(files)} file(s))")

def load_model():
    # try GPU first, fall back to CPU when cublas/cudnn (or a GPU) is missing
    for device, compute in [("cuda", "float16"), ("cuda", "float32"), ("cpu", "int8"), ("cpu", "auto")]:
        try:
            print(f"Trying faster-whisper {config.WHISPER_MODEL} on {device} ({compute}) ...")
            m = WhisperModel(config.WHISPER_MODEL, device=device, compute_type=compute)
            print(f"Loaded on {device} ({compute})")
            return m
        except Exception as e:
            msg = str(e).lower()
            if "cublas" in msg or "cudnn" in msg or "cuda" in msg or "invalid device" in msg:
                print(f"  {device} failed: {e} — trying fallback ...")
                continue
            raise
    raise RuntimeError("Could not load faster-whisper on any device")

model = load_model()

for file in files:
    base = os.path.splitext(file)[0]
    txt_out  = os.path.join(paths["TRANSCRIPTS_DIR"], base + ".txt")
    json_out = os.path.join(paths["TRANSCRIPTS_DIR"], base + "_segments.json")
    if os.path.exists(txt_out) and os.path.exists(json_out):
        print(f"Skipping {file} — already transcribed for {args.profile}.")
        continue
    path = os.path.join(src_dir, file)
    print(f"\nTranscribing {file} ...")
    segments, info = model.transcribe(path, language="en", vad_filter=True)
    full_text, seg_list = [], []
    for seg in segments:
        full_text.append(seg.text.strip())
        seg_list.append({"start": float(seg.start), "end": float(seg.end), "text": seg.text.strip()})
    text = " ".join(full_text)
    with open(txt_out, "w", encoding="utf-8") as f: f.write(text)
    with open(json_out, "w", encoding="utf-8") as f: json.dump({"duration": float(info.duration), "segments": seg_list}, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {txt_out} ({len(text)} chars)")
    print(f"  Saved: {json_out}  ({len(seg_list)} segments, {info.duration:.1f}s)")

print(f"\nDone [{args.profile}]. Next: python chunk_transcripts.py --profile {args.profile}")
