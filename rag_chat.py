# rag_chat.py — HadeS core RAG (global HH:MM:SS, profile-aware)
import os
# FORCE fully offline BEFORE any HF import — else WiFi-off = 2-min retry hang
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
import json, math, pickle, re
from collections import Counter, defaultdict
import requests
import faiss
import numpy as np
import config
# NOTE: SentenceTransformer is imported LAZILY inside get_model() so
# `import rag_chat` never touches huggingface.co (fixes offline import hang)

_model = None
_index = None
_metadata = None
_active_profile = None

def _profile(): return config.DEFAULT_PROFILE if _active_profile is None else _active_profile

def set_profile(name: str):
    global _index, _metadata, _active_profile, _bm25, _bm25_profile
    if name not in config.AVAILABLE_PROFILES:
        raise ValueError(f"Unknown profile {name!r}")
    if name != _active_profile:
        _active_profile = name
        _index = None; _metadata = None  # force reload
        _bm25 = None; _bm25_profile = None  # and the BM25 index

def list_profiles():
    out = []
    for name in config.AVAILABLE_PROFILES:
        p = config.profile_paths(name)
        ready = os.path.exists(p["INDEX_PATH"]) and os.path.exists(p["METADATA_PATH"])
        # chunk count from metadata or manifest
        n = 0
        try:
            if ready:
                with open(p["METADATA_PATH"], "rb") as f: n = len(pickle.load(f))
        except Exception: pass
        out.append({"name": name, "ready": ready, "chunks": n, "paths": p})
    return out

def _paths(): return config.profile_paths(_profile())

def _model_search_roots():
    """Roots to look for cached model snapshots, most specific first:
    $HADES_MODEL_DIR (explicit override / bundled app models), then ./models next to
    the app, then the HuggingFace cache in the user's home. No machine-specific literals."""
    import pathlib
    roots = []
    env_dir = os.environ.get("HADES_MODEL_DIR")
    if env_dir:
        roots.append(pathlib.Path(env_dir))
    if getattr(config, "BASE_DIR", None):
        roots.append(pathlib.Path(config.BASE_DIR) / "models")
    roots.append(pathlib.Path.home() / ".cache/huggingface/hub")
    return roots


def _local_snapshot():
    """Find cached snapshot so SentenceTransformer loads via local path — no hub hit."""
    import pathlib
    name = config.EMBEDDING_MODEL_NAME
    dirs = {name.replace("/", "--")}
    if "/" not in name:
        dirs.add(f"sentence-transformers--{name}")  # HF normalises bare names to this org
    for root in _model_search_roots():
        for d in dirs:
            base = root / f"models--{d}" / "snapshots"
            if not base.exists():
                continue
            # pick snapshot that has model.safetensors + config.json
            snaps = sorted(base.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
            for s in snaps:
                if (s / "model.safetensors").exists() or (s / "pytorch_model.bin").exists():
                    return str(s)
            if snaps: return str(snaps[0])
    return None

def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        # 1) try direct local snapshot path — instant, no hub DNS/retry when offline
        snap = _local_snapshot()
        if snap:
            try:
                _model = SentenceTransformer(snap, trust_remote_code=False, local_files_only=True)
                return _model
            except Exception:
                pass
        # 2) fallback: name + local_files_only
        try:
            _model = SentenceTransformer(config.EMBEDDING_MODEL_NAME, local_files_only=True, trust_remote_code=False)
        except Exception:
            _model = SentenceTransformer(config.EMBEDDING_MODEL_NAME)
    return _model

def get_index():
    global _index
    if _index is None:
        p = _paths()
        if not os.path.exists(p["INDEX_PATH"]):
            raise FileNotFoundError(f"No index for profile '{_profile()}' — run create_embeddings.py --profile {_profile()}")
        _index = faiss.read_index(p["INDEX_PATH"])
    return _index

def get_metadata():
    global _metadata
    if _metadata is None:
        p = _paths()
        if not os.path.exists(p["METADATA_PATH"]):
            raise FileNotFoundError(f"No metadata for profile '{_profile()}'")
        with open(p["METADATA_PATH"], "rb") as f: _metadata = pickle.load(f)
    return _metadata

def _fmt_time(sec):
    if sec is None: return "—"
    sec = int(round(float(sec))); h, sec = divmod(sec, 3600); m, s = divmod(sec, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def _pretty_label(m):
    start, end = m.get("start"), m.get("end")
    part = m.get("part", 0)
    # hades_demo single-file: part is "hades_demo" -> show just HH:MM:SS range
    try:
        if isinstance(part, str):
            nums = re.findall(r"\d+", part)
            if part == "hades_demo" or part.startswith("hades_demo"):
                if start is not None and end is not None:
                    return f"HadeS Demo — {_fmt_time(start)} – {_fmt_time(end)}"
                if start is not None:
                    return f"HadeS Demo — {_fmt_time(start)}"
                return m.get("source", "HadeS Demo")
            if nums:
                part = int(nums[0])
            else:
                # unknown string part -> show as-is
                if start is not None and end is not None:
                    return f"{part} — {_fmt_time(start)} – {_fmt_time(end)}"
                if start is not None:
                    return f"{part} — {_fmt_time(start)}"
                return m.get("source", str(part))
        part_int = int(part)
        if start is not None and end is not None:
            return f"Part {part_int:02d} — {_fmt_time(start)} – {_fmt_time(end)}"
        if start is not None:
            return f"Part {part_int:02d} — {_fmt_time(start)}"
        return m.get("source", f"Part {part_int:02d}")
    except Exception:
        return m.get("source", str(part))

def search_chunks(query, k=None):
    k = k or config.TOP_K_CHUNKS
    cands = _search_with_scores(query, k)
    ctx, labels, raw = [], [], []
    for c in cands:
        m = c["meta"]; ctx.append(m["text"]); labels.append(c["label"]); raw.append(m)
    return "\n\n---\n\n".join(ctx), labels, raw

# ── Hybrid retrieval: sparse BM25 + dense, fused with RRF (plan Phase 1.2) ──
# ponytail: BM25 stats are rebuilt lazily per profile (~1s for 1.3k chunks, dict
# counts, no inverted index) — swap in a real index only if a profile hits 100k chunks.
_bm25 = None
_bm25_profile = None

def _tokenize(text):
    """Lowercase words, keeping code-ish terms like f-string / pd.read_csv."""
    return re.findall(r"[a-z0-9]+(?:[._-][a-z0-9]+)*", (text or "").lower())

def _bm25_stats(docs):
    """Okapi BM25 corpus stats: per-doc term counts, idf, average length."""
    tf = [Counter(_tokenize(d)) for d in docs]
    df = Counter()
    for counts in tf:
        df.update(counts.keys())
    n = max(len(tf), 1)
    avgdl = (sum(sum(c.values()) for c in tf) / n) or 1.0
    idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
    return {"tf": tf, "idf": idf, "avgdl": avgdl}

def _bm25_scores(stats, query, k1=1.5, b=0.75):
    """{doc_id: BM25 score} over docs sharing at least one query term."""
    qterms = set(_tokenize(query))
    out = {}
    if not qterms:
        return out
    for i, counts in enumerate(stats["tf"]):
        dl = sum(counts.values())
        s = 0.0
        for t in qterms:
            f = counts.get(t)
            if not f:
                continue
            s += stats["idf"].get(t, 0.0) * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / stats["avgdl"]))
        if s:
            out[i] = s
    return out

def _rrf_fuse(rank_lists, k=60):
    """Reciprocal Rank Fusion → fused ids, best first."""
    scores = defaultdict(float)
    for ranks in rank_lists:
        for i, doc_id in enumerate(ranks):
            scores[doc_id] += 1.0 / (k + i + 1)
    return sorted(scores, key=scores.get, reverse=True)

def _bm25_for_profile():
    global _bm25, _bm25_profile
    if _bm25 is None or _bm25_profile != _profile():
        _bm25 = _bm25_stats([m.get("text", "") for m in get_metadata()])
        _bm25_profile = _profile()
    return _bm25

def _fused_cosine(index, qvec, doc_id, dense_scores):
    """True cosine for a fused id — from the dense pass, else reconstructed."""
    if doc_id in dense_scores:
        return dense_scores[doc_id]
    try:
        return float(np.dot(qvec, index.reconstruct(int(doc_id))))
    except Exception:
        return 0.0

# ── Cross-encoder rerank (plan Phase 1.3) — light MiniLM, offline cache ──
_reranker = None

def _get_reranker():
    global _reranker
    if _reranker is None:
        from sentence_transformers import CrossEncoder
        _reranker = CrossEncoder(config.RERANKER_MODEL)
    return _reranker

def rerank(query, candidates, top_k=None):
    """Reorder candidates by cross-encoder score; keeps RERANK_TOP_K of them.
    ponytail: falls back to the original order when the model can't load, so a
    missing cache degrades to the previous behaviour instead of breaking answers."""
    if not candidates:
        return candidates
    top_k = getattr(config, "RERANK_TOP_K", 6) if top_k is None else top_k
    try:
        scores = _get_reranker().predict([(query, c["text"]) for c in candidates])
    except Exception:
        return candidates[:top_k] if top_k else candidates
    ranked = sorted(zip(candidates, scores), key=lambda x: float(x[1]), reverse=True)
    return [c for c, _ in ranked[: top_k or len(ranked)]]

# ── Curated retrieval: A (LLM picks) + B (time-cluster dedup) ──
def _search_with_scores(query, k=None):
    """Candidates with cosine scores. RETRIEVE_MODE="hybrid" (default) fuses a
    dense pass with BM25 via RRF; "dense" keeps the old pure-FAISS path.
    Every caller (search_chunks / search_chunks_curated) routes through here."""
    k = k or config.TOP_K_CHUNKS
    mode = getattr(config, "RETRIEVE_MODE", "dense")
    rerank_on = getattr(config, "RERANK_ENABLED", False)
    pool = max(k, getattr(config, "RETRIEVE_K_HYBRID", 50)) if (mode == "hybrid" or rerank_on) else k
    model = get_model(); index = get_index(); meta = get_metadata()
    # bge v1.5 wants its retrieval instruction on the query only (documents stay raw)
    q = model.encode([getattr(config, "EMBEDDING_QUERY_PREFIX", "") + query], normalize_embeddings=True)
    faiss.normalize_L2(q)
    scores, I = index.search(q.astype("float32"), pool)
    dense = [(int(i), float(s)) for s, i in zip(scores[0], I[0]) if 0 <= int(i) < len(meta)]
    if mode == "hybrid":
        bm = _bm25_scores(_bm25_for_profile(), query)
        sparse = sorted(bm, key=bm.get, reverse=True)[:pool]
        known = dict(dense)
        fused = _rrf_fuse([[i for i, _ in dense], sparse], getattr(config, "RRF_K", 60))[:pool]
        ranked = [(i, _fused_cosine(index, q[0], i, known)) for i in fused]
    else:
        ranked = dense
    out = []
    for idx, score in ranked:
        m = meta[idx]
        out.append({
            "score": float(score),
            "meta": m,
            "label": _pretty_label(m),
            "text": m["text"],
            "start": m.get("start"),
            "end": m.get("end"),
            "part": m.get("part", 0),
            "youtube_url": _youtube_url_for(m.get("start")),
            })
    if rerank_on:
        out = rerank(query, out)
    return out[:k]


def _cluster_by_time(cands, window_sec=None):
    """Merge candidates whose start is within window_sec on same part. Return clusters (best first)."""
    if window_sec is None:
        window_sec = getattr(config, "CLUSTER_WINDOW_SEC", 300)
    clusters = []
    for cand in cands:
        placed = False
        for cl in clusters:
            rep = cl[0]
            if str(rep["part"]) != str(cand["part"]):
                continue
            if rep["start"] is None or cand["start"] is None:
                continue
            try:
                if abs(float(rep["start"]) - float(cand["start"])) <= window_sec:
                    cl.append(cand)
                    placed = True
                    break
            except Exception:
                continue
        if not placed:
            clusters.append([cand])
    # sort clusters by rep score desc (ensures deterministic)
    clusters.sort(key=lambda cl: cl[0]["score"], reverse=True)
    return clusters

def _best_snippet_for_cluster(cl, query):
    """Pick the chunk in cluster that best TEACHES query (not just highest cosine) for LLM prompt."""
    qwords = [w.lower() for w in re.findall(r"[a-zA-Z]+", query) if len(w) > 3]
    # score each member by teaching signal + cosine
    best = cl[0]; best_s = -1
    for m in cl:
        txt = m["text"].lower()
        hits = sum(1 for w in qwords if w in txt)
        define_bonus = 2 if "define" in txt else 0
        define_bonus += 1 if "definition" in txt or "syntax" in txt else 0
        # functions-specific: def keyword is strong
        if "function" in query.lower() and "def " in txt:
            define_bonus += 2
        s = m["score"] * 0.6 + hits * 0.12 + define_bonus * 0.15
        if s > best_s:
            best_s = s; best = m
    return best

def _teaching_score(cl, query):
    """Heuristic score so real lesson beats incidental mention — used when Ollama down (offline fallback)."""
    rep = cl[0]
    # cluster density = lesson (many adjacent chunks about same topic)
    size_bonus = min(len(cl) * 0.04, 0.25)
    max_score = max(c["score"] for c in cl)
    txt_all = " ".join(c["text"].lower() for c in cl)
    qlow = query.lower()
    # does the cluster actually define/teach the query term?
    define_bonus = 0
    if "define" in txt_all: define_bonus += 0.12
    if "definition" in txt_all or "syntax" in txt_all: define_bonus += 0.08
    if "function" in qlow and "def " in txt_all: define_bonus += 0.15
    if "variable" in qlow and ("variable" in txt_all and "name =" in txt_all): define_bonus += 0.10
    # penalize clearly off-topic rep (e.g., CSV file that happens to contain "function" once)
    # if top rep snippet is mostly about csv but cluster is about functions, penalize
    if "csv" in rep["text"].lower() and "function" in qlow and "def " not in rep["text"].lower():
        define_bonus -= 0.20
    if "dog" in rep["text"].lower() and "function" in qlow and len(cl) == 1 and "def " not in rep["text"].lower():
        define_bonus -= 0.10
    return max_score + size_bonus + define_bonus

def _ordered_main_clusters(query, cands, clusters, picked, main_k):
    """★ ordering: a confident dense top-1 (cosine ≥ MAIN_PRIOR_MIN_COSINE) leads; a weak
    one defers to the teaching score. Deterministic either way, so the same question stops
    changing which lesson shows first. A+B curation of the remaining picks still applies."""
    top = max(cands, key=lambda c: c["score"]) if cands else None
    prior = next((cl for cl in clusters if top is not None and any(c is top for c in cl)), None)
    if prior is None or top["score"] < getattr(config, "MAIN_PRIOR_MIN_COSINE", 0.5):
        return sorted(picked, key=lambda cl: _teaching_score(cl, query), reverse=True)
    if any(cl is prior for cl in picked):
        rest = [cl for cl in picked if cl is not prior]
    elif len(picked) >= main_k:
        rest = picked[: main_k - 1]  # curator dropped the confident top-1: swap the last pick out
    else:
        rest = list(picked)
    rest.sort(key=lambda cl: _teaching_score(cl, query), reverse=True)
    return [prior] + rest

def _llm_pick_main(query, clusters, main_k=None):
    """Ask local Ollama (offline) which clusters actually TEACH the query. Fallback to heuristic."""
    if main_k is None:
        main_k = getattr(config, "CURATED_MAIN_K", 2)
    if len(clusters) <= main_k:
        return list(range(len(clusters)))
    lines = []
    for i, cl in enumerate(clusters):
        # show the TEACHING-best snippet, not just top cosine rep
        show = _best_snippet_for_cluster(cl, query)
        snippet = show["text"][:280].replace("\n", " ").strip()
        cnt = len(cl)
        extra = f" +{cnt-1} nearby in same {int(getattr(config,'CLUSTER_WINDOW_SEC',300)/60)}min lesson" if cnt > 1 else ""
        span = ""
        try:
            starts = [float(x["start"]) for x in cl if x["start"] is not None]
            ends = [float(x["end"]) for x in cl if x["end"] is not None]
            if starts and ends and cnt > 1:
                span = f" span={_fmt_time(min(starts))}–{_fmt_time(max(ends))}"
        except Exception: pass
        lines.append(f"{i}. [{show['label']}{extra}{span}] score={show['score']:.3f} :: {snippet}")
    cand_block = "\n".join(lines)
    # Per-profile examples (G17): the Python-course examples used to be forced on every course.
    examples_block = getattr(config, "CURATOR_EXAMPLES", {}).get(_profile(), "")
    if examples_block:
        examples_block = "\n" + examples_block
    prompt = f"""You are HadeS retrieval curator. Query: "{query}"

Candidates (some just MENTION the word, some actually TEACH the full lesson). TEACH = the segment where the teacher introduces and explains the topic.

{cand_block}

Pick exactly {main_k} that ACTUALLY TEACH the query. Rules:
- Prefer a larger lesson (multiple nearby chunks) over a single mention.{examples_block}

Return ONLY JSON: {{"main": [idx, idx]}}
JSON:"""
    try:
        raw = ask_llm(prompt)
        import re as _re, json as _js
        m = _re.search(r"\{[^}]*\"main\"[^}]*\}", raw, _re.DOTALL)
        if m:
            j = _js.loads(m.group(0))
            picks = [int(x) for x in j.get("main", []) if isinstance(x, int) or (isinstance(x, str) and str(x).isdigit())]
            picks = [p for p in picks if 0 <= p < len(clusters)]
            seen = []
            for p in picks:
                if p not in seen: seen.append(p)
            if len(seen) == main_k:
                return seen
            if 1 <= len(seen) < main_k:
                # fill with heuristic best not already picked
                remaining = sorted([i for i in range(len(clusters)) if i not in seen],
                                   key=lambda i: _teaching_score(clusters[i], query), reverse=True)
                seen.extend(remaining[: main_k - len(seen)])
                return seen[:main_k]
    except Exception:
        pass
    # fallback: heuristic (offline) — no Ollama or bad JSON
    ranked = sorted(range(len(clusters)), key=lambda i: _teaching_score(clusters[i], query), reverse=True)
    return ranked[:main_k]

def search_chunks_curated(query, k=None, use_llm=True):
    """A+B retrieval: pull RETRIEVE_K -> cluster -> LLM pick CURATED_MAIN_K.
    Returns dict with main/also for UI and curated context for answer.
    Always works offline (LLM fallback to scores if Ollama down).
    """
    retrieve_k = getattr(config, "RETRIEVE_K", 12)
    top_k = k or config.TOP_K_CHUNKS
    main_k = getattr(config, "CURATED_MAIN_K", 2)
    cands = _search_with_scores(query, retrieve_k)
    if not cands:
        return {"context": "", "labels": [], "details": [], "main": [], "also": [], "main_context": "", "clusters": []}
    clusters = _cluster_by_time(cands)
    # LLM pick (offline) — heuristic fallback when Ollama down (never raw cosine)
    if use_llm and getattr(config, "OLLAMA_API_URL", None):
        try:
            main_idx = _llm_pick_main(query, clusters, main_k)
        except Exception:
            ranked = sorted(range(len(clusters)), key=lambda i: _teaching_score(clusters[i], query), reverse=True)
            main_idx = ranked[:main_k]
    else:
        ranked = sorted(range(len(clusters)), key=lambda i: _teaching_score(clusters[i], query), reverse=True)
        main_idx = ranked[:main_k]
    main_clusters = _ordered_main_clusters(query, cands, clusters, [clusters[i] for i in main_idx], main_k)
    also_clusters = [c for c in clusters if all(c is not m for m in main_clusters)]
    # cap also to fill top_k total lessons
    also_clusters = also_clusters[: max(0, top_k - len(main_clusters))]
    # Build UI details: one rep per cluster, but keep cluster size info
    def to_detail(cl):
        rep = cl[0]
        label = rep["label"]
        # if cluster has multiple chunks, show merged span
        if len(cl) > 1:
            try:
                starts = [float(x["start"]) for x in cl if x["start"] is not None]
                ends = [float(x["end"]) for x in cl if x["end"] is not None]
                if starts and ends:
                    label = rep["label"].split("—")[0].strip() + f" — {_fmt_time(min(starts))} – {_fmt_time(max(ends))} ({len(cl)} chunks)"
            except Exception:
                pass
        return {
            "label": label,
            "text": rep["text"][:600],
            "start": rep["start"], "end": rep["end"], "part": rep["part"],
            "youtube_url": rep["youtube_url"],
            "score": rep["score"],
            "cluster_size": len(cl),
            "cluster": cl,
        }
    main_details = [to_detail(cl) for cl in main_clusters]
    also_details = [to_detail(cl) for cl in also_clusters]
    # Context for answer: join main representative texts (most grounded) + also if needed
    main_context = "\n\n---\n\n".join(cl[0]["text"] for cl in main_clusters)
    also_context = "\n\n---\n\n".join(cl[0]["text"] for cl in also_clusters)
    full_context = main_context + ("\n\n---\n\n" + also_context if also_context else "")
    # compat: labels/details = main+also
    all_details = main_details + also_details
    all_labels = [d["label"] for d in all_details]
    return {
        "context": full_context,
        "labels": all_labels,
        "details": all_details,
        "main": main_details,
        "also": also_details,
        "main_context": main_context,
        "clusters": clusters,
        "raw_cands": cands,
    }

def _youtube_url_for(start_sec):
    base = config.YOUTUBE_URLS.get(_profile()) if hasattr(config, "YOUTUBE_URLS") else None
    if not base or start_sec is None:
        return None
    try:
        sec = int(round(float(start_sec)))
    except Exception:
        return None
    # youtu.be/xxx  →  youtu.be/xxx?t=123s  (or &t= if already ?)
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}t={sec}s"

# ── Refusal + grounding validation (plan Phases 2.2 / 2.3) ──
def curated_confidence(curated):
    """Best cosine retrieval produced for this question; 0.0 when nothing was found.

    It reads the retrieved candidate pool, not only the clusters the curator picked.
    Keying it off the picks made the refusal gate flip on the same question: measured
    on `og`, 'What are functions?' scored 0.234 (declined) through the picks while the
    pool carries a legible lesson - and the identical question answered minutes earlier.
    """
    best = 0.0
    for d in list(curated.get("main", [])) + list(curated.get("also", [])) + list(curated.get("raw_cands", [])):
        try:
            best = max(best, float(d.get("score") or 0.0))
        except (TypeError, ValueError):
            pass
    return best

def _split_sentences(text):
    return [p.strip(" *`_-#") for p in re.split(r"(?<=[.!?])\s+|\n+", text or "") if len(p.strip()) > 20]

def validate_grounding(answer, chunks, threshold=None, pass_ratio=None):
    """Per-claim support: cosine(claim, cited lesson). One MiniLM batch, no LLM."""
    threshold = config.GROUNDING_THRESHOLD if threshold is None else threshold
    pass_ratio = config.GROUNDING_PASS_RATIO if pass_ratio is None else pass_ratio
    texts = [c.get("text", "") for c in chunks if c.get("text")]
    claims = _split_sentences(answer)
    if not claims or not texts:
        return {"overall": 0.0, "claims": [], "passed": False}
    try:
        embs = np.asarray(get_model().encode(claims + texts, normalize_embeddings=True), dtype="float32")
    except Exception:
        return {"overall": 0.0, "claims": [], "passed": False}
    sims = embs[: len(claims)] @ embs[len(claims):].T
    best = sims.max(axis=1)
    out = [{"claim": c, "support": float(s), "verified": bool(s >= threshold)} for c, s in zip(claims, best)]
    overall = sum(c["verified"] for c in out) / len(out)
    return {"overall": float(overall), "claims": out, "passed": overall >= pass_ratio}

def _ollama_payload(prompt: str, stream: bool) -> dict:
    """Request body for /api/generate. keep_alive keeps the model loaded so the
    next question doesn't pay the ~25s cold-load stall again."""
    return {
        "model": config.OLLAMA_MODEL_NAME,
        "prompt": prompt,
        "stream": stream,
        "options": {"temperature": config.LLM_TEMPERATURE, "num_predict": config.LLM_MAX_TOKENS},
        "keep_alive": getattr(config, "OLLAMA_KEEP_ALIVE", "5m"),
    }

def ask_llm(prompt: str) -> str:
    r = requests.post(config.OLLAMA_API_URL, json=_ollama_payload(prompt, False), timeout=120)
    r.raise_for_status(); return r.json().get("response","").strip()

def warmup_llm() -> None:
    """Load the model into Ollama's memory before the first question. Best effort:
    a real request still reports a missing model or a dead Ollama properly."""
    try:
        requests.post(
            config.OLLAMA_API_URL,
            json={
                "model": config.OLLAMA_MODEL_NAME,
                "prompt": ".",
                "stream": False,
                "options": {"num_predict": 1},
                "keep_alive": getattr(config, "OLLAMA_KEEP_ALIVE", "5m"),
            },
            timeout=300,
        )
    except Exception:
        pass

def ask_llm_stream(prompt: str):
    r = requests.post(config.OLLAMA_API_URL, json=_ollama_payload(prompt, True), stream=True, timeout=120)
    r.raise_for_status()
    for line in r.iter_lines():
        if not line: continue
        try: j=json.loads(line)
        except: continue
        t=j.get("response","")
        if t: yield t
        if j.get("done"): break
