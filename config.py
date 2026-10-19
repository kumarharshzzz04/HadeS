# config.py
# ==============================================================================
# CONFIGURATION — HadeS | Teaching Assistant
# Modify values here; all scripts read from this single source.
# ==============================================================================
import json
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- 1. Directory paths (OG = top-level, profiles live under profiles/<name>) ---
VIDEO_DIR       = os.path.join(BASE_DIR, "video")
AUDIO_DIR       = os.path.join(BASE_DIR, "audios")
TRANSCRIPTS_DIR = os.path.join(BASE_DIR, "transcripts")
CHUNKS_DIR      = os.path.join(BASE_DIR, "chunks")
INDEX_PATH    = os.path.join(BASE_DIR, "faiss_index.bin")
METADATA_PATH = os.path.join(BASE_DIR, "metadata.pkl")

PROFILES_DIR = os.path.join(BASE_DIR, "profiles")
# og = current 18h top-level index; hades_demo = new 3-4h exact-timestamp index
AVAILABLE_PROFILES = ["og", "hades_demo", "quantum"]
# hades_demo, not og (plan Task 0.10 / G12): og is the estimated-timestamp 18h set with no single
# source video, so a first run on it hands the user citations that cannot be clicked.
DEFAULT_PROFILE = "hades_demo"

def state_dir() -> str:
    """Writable per-user state (settings, model bookkeeping) that survives a read-only
    install dir (plan Task 2.3). %LOCALAPPDATA%/HadeS by default, HADES_STATE_DIR overrides."""
    d = os.environ.get("HADES_STATE_DIR") or os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "HadeS"
    )
    os.makedirs(d, exist_ok=True)
    return d


def profile_paths(name: str) -> dict:
    """Return paths for a profile. 'og' uses top-level; others use profiles/<name>/."""
    if name == "og":
        return {
            "TRANSCRIPTS_DIR": TRANSCRIPTS_DIR,
            "CHUNKS_DIR": CHUNKS_DIR,
            "INDEX_PATH": INDEX_PATH,
            "METADATA_PATH": METADATA_PATH,
            "MANIFEST": os.path.join(CHUNKS_DIR, "_chunk_manifest.json"),
        }
    base = os.path.join(PROFILES_DIR, name)
    return {
        "TRANSCRIPTS_DIR": os.path.join(base, "transcripts"),
        "CHUNKS_DIR": os.path.join(base, "chunks"),
        "INDEX_PATH": os.path.join(base, "faiss_index.bin"),
        "METADATA_PATH": os.path.join(base, "metadata.pkl"),
        "MANIFEST": os.path.join(base, "chunks", "_chunk_manifest.json"),
    }

# --- 2. AI model configuration ---
# bge-small-en-v1.5 was tried here (Oct 2026, 129 MB, same 384 dims, with rerank): it
# scored 6/11 vs MiniLM's 8/11 on the EVAL sweep and flattened similarity margins (junk
# chunks at 0.79 vs teaching moments at 0.78), filling the rerank pool with near-ties and
# breaking grounding validation (hallucinated claims hit 0.45-0.78). MiniLM wins on THIS
# corpus + A+B + rerank stack — re-run the sweep before swapping again.
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_QUERY_PREFIX = ""  # only for models that need a retrieval instruction (bge v1.5)
WHISPER_MODEL        = "small"
def load_settings() -> dict:
    """User settings from state_dir()/settings.json. Missing/corrupt file = empty dict."""
    try:
        with open(os.path.join(state_dir(), "settings.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def save_settings(**kv) -> None:
    s = load_settings()
    s.update(kv)
    with open(os.path.join(state_dir(), "settings.json"), "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)


# The default; the setup screen can switch it and remembers the choice in settings.json.
OLLAMA_MODEL_NAME    = os.environ.get("HADES_MODEL") or load_settings().get("model") or "llama3:8b"
# Ollama endpoint — ONE source of truth: every URL derives from the host, env-overridable (plan B1/B2).
OLLAMA_HOST          = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_API_URL       = f"{OLLAMA_HOST}/api/generate"
OLLAMA_TAGS_URL      = f"{OLLAMA_HOST}/api/tags"

# What the setup screen offers. 3B first: the target machine is CPU-only (plan decisions).
OFFERED_MODELS = (
    {"name": "llama3.2:3b", "label": "llama3.2:3b", "size": "~2 GB", "note": "faster on CPU"},
    {"name": "llama3:8b", "label": "llama3:8b", "size": "~4.7 GB", "note": "better answers"},
)

# --- 2b. Source video links (for clickable HH:MM:SS → YouTube seek; offline: just a link, no fetch) ---
# single public YouTube sources per profile; og = 18h local cut, no single link
YOUTUBE_URLS = {
    "hades_demo": "https://youtu.be/ygXn5nV5qFc",
    "quantum": "https://youtu.be/tsbCSkvHhMo",
}

# --- 3. Generation parameters ---
LLM_TEMPERATURE = 0.25
LLM_MAX_TOKENS  = 900
CHAT_HISTORY_TURNS = 3

# --- 3b. Model residency (Ollama) ---
# Ollama's default 5-minute unload means a pause between questions pays the full
# model-load stall again (measured: first token at 25-33s instead of ~2s).
# Keeping the model resident is what makes answers stream steadily all session.
OLLAMA_KEEP_ALIVE  = "6h"
LLM_WARMUP_ENABLED = True  # load the model at server start, before the first question

# --- 4. Retrieval parameters ---
TOP_K_CHUNKS = 5
RETRIEVE_K = 12          # pull 12, then curate to TOP_K (A+B)
CURATED_MAIN_K = 2       # ★ Main lesson count
CLUSTER_WINDOW_SEC = 300 # B: merge chunks within 5 min into one lesson

# --- 4b. Hybrid retrieval: sparse BM25 + dense, fused with Reciprocal Rank Fusion ---
# Measured on EVAL 11/11 (hades_demo): RRF moves top-1 on 9/11 questions and lands
# wrong chapters on 4 (f-string -> end-of-video recap, "create venv" -> unrelated) —
# BM25 favours recap sections over the teaching moment. Keep "dense" until a
# reranker filters the fused pool (plan Phase 1.3); "hybrid" is the opt-in for then.
RETRIEVE_MODE     = "dense"   # "dense" (default) | "hybrid" (BM25 + dense + RRF)
RETRIEVE_K_HYBRID = 50        # candidates per channel before fusion
RRF_K             = 60        # RRF constant (Cormack et al.)

# ★ main-lesson prior: a dense top-1 at/above this cosine leads the mains; below it the
# A+B teaching score decides. Measured on EVAL: strong tops (strings 0.700, pip 0.642) are
# right; weak tops (functions 0.484) are noise that the teaching heuristic must demote.
MAIN_PRIOR_MIN_COSINE = 0.5

# --- 4b2. Curator LLM switch (plan Task 0.8) ---
# ON means every question runs a SECOND Ollama generation just to pick which lesson teaches it;
# OFF uses the existing _teaching_score heuristic (never raw cosine) plus the dense-top-1 prior.
# TIMESTAMP_AUDIT.md measured both curators over 152 retrieval runs: first-MAIN hits are a wash
# on hades_demo (7/8/7 vs 7/8/7) and the heuristic edges it on quantum (ask 8/10 vs 7/10).
# Latency delta is measured in Task 0.8 (see the plan).
LLM_CURATOR_ENABLED = False

# --- 4c. Cross-encoder rerank (light MiniLM; plan's bge-reranker-v2-m3 = 2.3 GB, too heavy) ---
# Enabled from the 4-way sweep (dense/hybrid x rerank off/on, 11 EVAL questions):
# rerank fixes data-types (03:48 -> 01:09:39) and programming (intro -> 00:51 chapter)
# for +0.8s/query and 0.4s cold load; hybrid+rerank matches dense+rerank, so BM25
# noise adds nothing here -> keep RETRIEVE_MODE="dense".
RERANK_ENABLED = True
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"  # 22.7M params, ~88 MB, cached offline
RERANK_TOP_K   = 6       # reranked candidates kept for clustering + A+B curation

# --- 4d. Refusal + grounding validation (thresholds tuned on EVAL.md sweep) ---
REFUSAL_ENABLED          = True
MIN_RETRIEVAL_CONFIDENCE = 0.35  # with rerank: EVAL-11 min 0.371 vs off-topic max 0.251
# OFF by default (plan Task 0.7): the payload field was never read by any frontend version
# (git log -S"validation" -- frontend/ → 0 commits) and it costs a MiniLM batch over every
# claim + cited lesson on every answer. validate_grounding() is kept — TIMESTAMP_AUDIT work
# still uses it. Flip this to True to put the field back in /api/ask payloads.
GROUNDING_VALIDATION     = False
GROUNDING_THRESHOLD      = 0.35  # measured: grounded claims 0.49-0.54, hallucinated 0.06-0.61
GROUNDING_PASS_RATIO     = 0.8   # fraction of supported claims needed to pass

# --- 4e. Curator prompt examples, per profile (plan Task 0.6 / findings G17-G18) ---
# The curator prompt hardcoded Python-course examples (and a code-shaped definition of TEACH)
# for EVERY profile. On the quantum course those are meaningless and bias the pick. One string
# per profile, already bullet-prefixed; a profile with no entry simply gets no examples line.
_CURATOR_EXAMPLES_PYTHON = (
    '- TEACH means the video segment where the teacher introduces and explains the topic '
    '(e.g., "Defining functions", "What is a variable"). Incidental mentions like '
    '"take a CSV file, do calculations" (mentions function once), "methods are functions", '
    '"dog breed error" are NOT teaching.\n'
    '- If query is "what are functions", the lesson is around 02:06-02:10 Defining Functions, '
    'NOT 02:28 CSV or 03:48 classes.'
)
_CURATOR_EXAMPLES_QUANTUM = (
    '- TEACH means the segment where the teacher introduces and explains the topic '
    '(e.g., "Introduction to Qubit", "What is superposition"). A passing reference inside an '
    'unrelated topic is NOT teaching.'
)
CURATOR_EXAMPLES = {
    "og": _CURATOR_EXAMPLES_PYTHON,
    "hades_demo": _CURATOR_EXAMPLES_PYTHON,
    "quantum": _CURATOR_EXAMPLES_QUANTUM,
}

# --- 5. Chunking parameters ---
CHUNK_SIZE    = 1000
CHUNK_OVERLAP = 200
