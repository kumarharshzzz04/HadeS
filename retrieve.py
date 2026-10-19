import faiss, pickle, os
import config
from sentence_transformers import SentenceTransformer

# Simple CLI test for HadeS retrieval — uses config.py, no hardcoded paths.
# Run: python retrieve.py

if not os.path.exists(config.INDEX_PATH):
    print(f"Missing index: {config.INDEX_PATH} — run python create_embeddings.py first")
    exit(1)

print("Loading embedding model...")
model = SentenceTransformer(config.EMBEDDING_MODEL_NAME)
print("Loading FAISS index...")
index = faiss.read_index(config.INDEX_PATH)
print("Loading metadata...")
with open(config.METADATA_PATH, "rb") as f:
    metadata = pickle.load(f)
print(f"Loaded {len(metadata)} chunks. Index metric: {index.metric_type} (1=IP cosine, 0=L2)")

while True:
    query = input("\nAsk a question (or type exit): ")
    if query.lower() == "exit":
        break
    print("Searching...")
    # normalized for IP index
    try:
        import numpy as np
        q = model.encode([query], normalize_embeddings=True).astype("float32")
    except TypeError:
        import numpy as np
        q = model.encode([query])
        q = q / np.linalg.norm(q, axis=1, keepdims=True)
        q = q.astype("float32")
    k = config.TOP_K_CHUNKS
    scores, indices = index.search(q, k)
    print(f"\nTop {k} results (score = cosine):\n")
    for rank, i in enumerate(indices[0]):
        meta = metadata[i] if 0 <= i < len(metadata) else {}
        fname = meta.get("source", f"idx_{i}")
        text = meta.get("text", "")
        if not text:
            fp = os.path.join(config.CHUNKS_DIR, fname)
            try:
                with open(fp, "r", encoding="utf-8") as f: text = f.read()
            except: text = ""
        s, e = meta.get("start"), meta.get("end")
        label = fname
        if s is not None:
            m, sec = int(s//60), int(s%60)
            label = f"{fname} — {m:02d}:{sec:02d}"
            if e is not None:
                m2, s2 = int(e//60), int(e%60)
                label += f"–{m2:02d}:{s2:02d}"
        print(f"[{rank+1}] {label}  (score {scores[0][rank]:.3f})")
        print(text[:600].replace("\n"," "))
        print("\n" + "-"*60 + "\n")
