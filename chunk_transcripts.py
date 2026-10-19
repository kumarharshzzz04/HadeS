import os, json, re, argparse
import config

parser = argparse.ArgumentParser()
parser.add_argument("--profile", default="og", choices=config.AVAILABLE_PROFILES, help="og = 18h index, hades_demo = new 3-4h video")
args = parser.parse_args()
paths = config.profile_paths(args.profile)

os.makedirs(paths["CHUNKS_DIR"], exist_ok=True)

CHUNK_SIZE = config.CHUNK_SIZE
OVERLAP    = config.CHUNK_OVERLAP
# HadeS Demo (5h clean speech) -> tighter chunks so Variables intro stays pure, not mixed with previous syntax section
if args.profile == "hades_demo":
    CHUNK_SIZE = 700
    OVERLAP = 100
# Quantum Computing course (1h36 clean lecture) -> same tighter treatment
if args.profile == "quantum":
    CHUNK_SIZE = 700
    OVERLAP = 100

def chunk_text_smart(text: str):
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + CHUNK_SIZE, n)
        if end < n:
            window = text[start:end]
            for sep in [". ", ".\n", "? ", "! ", "\n", " "]:
                idx = window.rfind(sep)
                if idx > CHUNK_SIZE * 0.5:
                    end = start + idx + len(sep)
                    break
        chunk = text[start:end].strip()
        if chunk:
            chunks.append((chunk, start, end))
        if end >= n:
            break
        start = end - OVERLAP
        if start < 0: start = 0
    return chunks

def load_segments_for(base: str):
    seg_path = os.path.join(paths["TRANSCRIPTS_DIR"], base + "_segments.json")
    if not os.path.exists(seg_path): return None
    try:
        with open(seg_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("segments", [])
    except Exception: return None

def estimate_timestamps(seg_list, full_text, chunk_start_char, chunk_end_char, part_duration_sec=None):
    # Exact mapping: chunk char offset -> Whisper segment time (no proportional drift)
    if seg_list:
        # Build char offset -> time map from segments (same join as transcript: " ".join)
        offsets = []  # (char_start, char_end, time_start, time_end)
        pos = 0
        for s in seg_list:
            txt = s["text"] + " "
            offsets.append((pos, pos + len(txt), float(s["start"]), float(s["end"])))
            pos += len(txt)
        total_chars = pos
        # If transcript length matches recon, use direct offset lookup (exact)
        if total_chars and abs(total_chars - len(full_text)) < 200:
            def time_at(char_pos):
                # clamp
                if char_pos <= 0: return offsets[0][2]
                if char_pos >= total_chars: return offsets[-1][3]
                for cs, ce, ts, te in offsets:
                    if cs <= char_pos < ce:
                        return ts
                return offsets[-1][3]
            s = time_at(chunk_start_char)
            e = time_at(chunk_end_char)
            # ensure e is segment end, not just start
            for cs, ce, ts, te in offsets:
                if cs <= chunk_end_char < ce:
                    e = te
                    break
            if e <= s: e = s + 60
            return round(s, 1), round(e, 1)
        # Fallback: search chunk text in recon (handles re-formatted transcripts)
        recon = " ".join(s["text"] for s in seg_list)
        # we need chunk text to search — caller passes full_text + offsets, so search chunk slice
        chunk_text = full_text[chunk_start_char:chunk_end_char]
        needle = chunk_text[:120].strip()
        idx = recon.find(needle[:60]) if needle else -1
        if idx >= 0:
            def time_at_search(cpos):
                for cs, ce, ts, te in offsets:
                    if cs <= cpos < ce: return ts
                return offsets[0][2] if cpos < offsets[0][0] else offsets[-1][3]
            s = time_at_search(idx)
            e = time_at_search(idx + len(chunk_text))
            for cs, ce, ts, te in offsets:
                if cs <= idx + len(chunk_text) < ce:
                    e = te; break
            return round(s, 1), round(e, 1)
        # last resort: proportional (should not happen for hades_demo)
        total_dur = float(seg_list[-1]["end"])
        s = (chunk_start_char / len(full_text)) * total_dur if len(full_text) else 0
        e = (chunk_end_char / len(full_text)) * total_dur if len(full_text) else total_dur
        return round(s, 1), round(e, 1)
    if part_duration_sec and len(full_text):
        p0 = chunk_start_char / len(full_text)
        p1 = chunk_end_char / len(full_text)
        s = round(p0 * part_duration_sec)
        e = round(p1 * part_duration_sec)
        if e - s < 40: e = min(s + 65, part_duration_sec)
        return int(s), int(e)
    return None, None

if not os.path.exists(paths["TRANSCRIPTS_DIR"]):
    print(f"No transcripts folder: {paths['TRANSCRIPTS_DIR']}")
    exit(0)

files = sorted(f for f in os.listdir(paths["TRANSCRIPTS_DIR"]) if f.endswith(".txt") and not f.endswith("_segments.json"))
if not files:
    print("No transcript .txt files found.")
    exit(0)

# durations for fallback (only used when no _segments.json — exact times are from Whisper segments)
part_durations = {}
for fname in files:
    base = fname.replace(".txt","")
    seg = load_segments_for(base)
    if seg:
        # real duration will be used via seg_list path, this is just fallback guard
        part_durations[base] = round(seg[-1]["end"]) if seg else 3600
    elif args.profile == "og":
        part_durations[base] = 60 if base == "part_018" else 3600  # 18h cut equal = 60m each
    else:
        # hades_demo single 3-4h file without segments: estimate from text length ~750 chars/min
        txt = open(os.path.join(paths["TRANSCRIPTS_DIR"], fname), encoding="utf-8").read()
        part_durations[base] = max(60, round(len(txt) / 750 * 60))

manifest = {}
for file in files:
    base = file.replace(".txt", "")
    path = os.path.join(paths["TRANSCRIPTS_DIR"], file)
    with open(path, "r", encoding="utf-8") as f: text = f.read()
    seg_list = load_segments_for(base)
    chunks = chunk_text_smart(text)
    dur = part_durations.get(base, 3600)
    print(f"{file}: {len(text)} chars -> {len(chunks)} chunks" + (" (real timestamps)" if seg_list else f" (est ~{dur//60:02d}:{dur%60:02d})"))
    for i, (chunk, c_start, c_end) in enumerate(chunks):
        chunk_file = f"{base}_chunk_{i}.txt"
        chunk_path = os.path.join(paths["CHUNKS_DIR"], chunk_file)
        with open(chunk_path, "w", encoding="utf-8") as f: f.write(chunk)
        s, e = estimate_timestamps(seg_list, text, c_start, c_end, dur)
        manifest[chunk_file] = {"start": s, "end": e, "part": base}

manifest_path = paths["MANIFEST"]
with open(manifest_path, "w", encoding="utf-8") as f: json.dump(manifest, f, indent=2)

print(f"\nChunking complete [{args.profile}]. {len(manifest)} chunks. Manifest: {manifest_path}")
print(f"Next: python create_embeddings.py --profile {args.profile}")
