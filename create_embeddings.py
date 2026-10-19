# create_embeddings.py — HadeS, profile-aware
# Usage:
#   python create_embeddings.py                  # og  (18h)
#   python create_embeddings.py --profile hades_demo   # 3-4h demo
import os, json, pickle, re, argparse
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import config

parser = argparse.ArgumentParser()
parser.add_argument("--profile", default="og", choices=config.AVAILABLE_PROFILES)
args = parser.parse_args()
paths = config.profile_paths(args.profile)

print(f"Profile: {args.profile}")
print(f"  chunks: {paths['CHUNKS_DIR']}")
print(f"  index:  {paths['INDEX_PATH']}")
print(f"Loading embedding model: {config.EMBEDDING_MODEL_NAME} ...")
model = SentenceTransformer(config.EMBEDDING_MODEL_NAME)

if not os.path.exists(paths["CHUNKS_DIR"]):
    print(f"  {paths['CHUNKS_DIR']} not found. Run chunk_transcripts.py --profile {args.profile} first.")
    exit(1)

manifest = {}
manifest_path = paths["MANIFEST"]
if os.path.exists(manifest_path):
    try:
        with open(manifest_path, "r", encoding="utf-8") as f: manifest = json.load(f)
        print(f"Loaded chunk manifest: {len(manifest)} entries with timestamps")
    except Exception as e: print(f"  Could not read manifest: {e}")

def fallback_timestamp(chunk_file: str):
    info = manifest.get(chunk_file)
    if info and info.get("start") is not None:
        return info["start"], info["end"], info.get("part","")
    m = re.match(r"(.+)_chunk_\d+\.txt", chunk_file)
    if m: return None, None, m.group(1)
    return None, None, ""

chunk_files = sorted(f for f in os.listdir(paths["CHUNKS_DIR"]) if f.endswith(".txt") and not f.startswith("_"))
if not chunk_files:
    print("  No chunk .txt files found.")
    exit(1)

documents, metadata = [], []
for fname in chunk_files:
    path = os.path.join(paths["CHUNKS_DIR"], fname)
    with open(path, "r", encoding="utf-8") as f: text = f.read()
    documents.append(text)
    s, e, part = fallback_timestamp(fname)
    metadata.append({"source": fname, "text": text, "start": s, "end": e, "part": part})

print(f"Total chunks: {len(documents)}")
print("Encoding (normalized for cosine/IP) ...")
embeddings = model.encode(documents, show_progress_bar=True, normalize_embeddings=True)
embeddings = np.array(embeddings, dtype="float32")
dimension = embeddings.shape[1]
print(f"Embedding dim: {dimension}  (normalized, using Inner Product)")
os.makedirs(os.path.dirname(paths["INDEX_PATH"]) or ".", exist_ok=True)
index = faiss.IndexFlatIP(dimension)
index.add(embeddings)
print(f"FAISS index: {index.ntotal} vectors, metric=IP (cosine)")
faiss.write_index(index, paths["INDEX_PATH"])
print(f"Saved index -> {paths['INDEX_PATH']}")
with open(paths["METADATA_PATH"], "wb") as f: pickle.dump(metadata, f)
print(f"Saved metadata -> {paths['METADATA_PATH']}  ({len(metadata)} entries)")

try:
    q = model.encode([getattr(config, "EMBEDDING_QUERY_PREFIX", "") + "machine learning introduction"], normalize_embeddings=True).astype("float32")
    scores, ids = index.search(q, 3)
    print(f"Self-test query scores: {scores[0].tolist()}  ids: {ids[0].tolist()}")
except Exception as e: print(f"Self-test skipped: {e}")
print(f"Done [{args.profile}].")
