# HadeS Desktop App — Implementation Plan

> **For agentic workers:** this plan is executed batch by batch. A batch is done only when its
> "Done when" gate passes. Do not start the next batch until the gate passes, unless the batch is
> marked `independent`. Steps use `- [ ]` checkboxes.

**Goal:** Ship HadeS as a Windows desktop app a non-technical user can install, that guides them
through getting Ollama running and downloads the model for them, and that runs from any folder on
any machine.

**Architecture:** Keep the current shape — React UI + FastAPI over `rag_chat.py` — and wrap it.
The Python sidecar is frozen into a single bundled executable. FastAPI also serves the React build
as static files, which removes the Vite proxy and the CORS allowlist in one move. Ollama stays a
separate install; the app detects it, starts it, and pulls models through its HTTP API.

**Tech Stack:** Python 3.12 (see Batch 2.1), FastAPI, uvicorn, faiss-cpu, sentence-transformers,
torch (CPU), React 19 + Vite 8, Ollama HTTP API.

**Spec:** the decisions in this document, plus `TIMESTAMP_AUDIT.md` for the retrieval findings.
There is no separate design doc; where a value is decided it is written here verbatim.

## Global Constraints

- Windows 10 22H2 or newer. Ollama requires it; so do we.
- Never require Administrator. Ollama's own installer does not, so ours must not either.
- Target install budget: under 1.5 GB excluding Ollama and the LLM model.
- Ollama and its models are never bundled in Batch 0-3. Only Batch 4 considers it.
- Python must be pinned and owned by the app. The dev machine's interpreter is a user-scope
  Python 3.14 install in `%APPDATA%`; the app must not depend on it.
- Every hardcoded value removed in Batch 0 gets one source of truth, read from config, and is
  env-overridable. No duplicate literals.
- No new dependencies for Batch 0. It is a refactor.
- `frontend/dist` is a build artifact, not committed. Any task that bundles or serves the UI
  must run `cd frontend && npm run build` first, or it will silently package nothing.
- Hand-run baseline at plan time — there is **no CI** (`.github/` does not exist) and
  `frontend/package.json` has no test script. Verified: `python -m pytest tests/ -q` → **9 passed**
  in 0.61s; `cd frontend && node scripts/quiz.check.ts && node scripts/sources.check.ts &&
  node scripts/stream-text.check.ts` → three `ok` lines (Node 23+ strips types). A task touching
  frontend behaviour must run the node checks; a task touching Python must run pytest.
- `rag_chat.py` retrieval behaviour must not change in Batch 0-3. This plan is about packaging,
  not about the timestamp findings.

---

## HARDCODED INVENTORY

Everything below must be audited. `KEEP` means deliberately left as-is and why.

### A. Machine-specific paths

| # | Location | Value | Action |
|---|---|---|---|
| A1 | `rag_chat.py:56` | `pathlib.Path(r"C:/Users/kingh/.cache/huggingface/hub")` second search root | **CRITICAL.** Hardcoded user path. Remove; resolve from env then home then bundled `.\models`. Breaks on every other machine today. |
| A2 | `rag_chat.py:52-56` | dirs set built from `config.EMBEDDING_MODEL_NAME`, plus the `sentence-transformers--` variant | KEEP logic. It is the correct HF cache layout. Only the roots list is wrong. |
| A3 | `config.py:7` | `BASE_DIR = os.path.dirname(os.path.abspath(__file__))` | KEEP. Portable. Keep using it for all data paths. |
| A4 | `dev.py:346` | `%LOCALAPPDATA%\Programs\Ollama\ollama.exe` | KEEP. Documented real install location. |
| A5 | `dev.py:347` | `C:\Program Files\Ollama\ollama.exe` | KEEP. Documented alternate. |
| A6 | `download_hades_demo.py` | video download target | KEEP. Dev tool, not shipped. |

### B. Hosts, ports, URLs

| # | Location | Value | Action |
|---|---|---|---|
| B1 | `config.py:51` | `OLLAMA_API_URL = "http://localhost:11434/api/generate"` | Move host/port to `OLLAMA_HOST` env with this default. Keep the `/api/generate` suffix in code. |
| B2 | `dev.py:46` | `OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags"` | Duplicate of B1. Derive from B1's base so the two cannot drift. |
| B3 | `dev.py:44` | `HOST = "127.0.0.1"` | KEEP. Loopback only is correct for a desktop app. |
| B4 | `dev.py:45` | `BACKEND_PORT = 8000` | Keep default, allow env override. Sidecar should pick a free port at runtime and tell the shell. |
| B5 | `dev.py:48` | `CANDIDATE_PORTS = tuple(range(5173, 5180))` | Dev-only. Delete once FastAPI serves the build (3.2). |
| B6 | `server.py:32-39` | CORS `allow_origins` = 4 literals on ports 5173/5174 | **Breaks a packaged app.** Deleted in 3.2 when the sidecar serves the UI same-origin. Until then, env-overridable. |
| B7 | `server.py:300` | `uvicorn.run(app, host="127.0.0.1", port=8000)` | Read host/port from env. Port `0` means "pick a free one", needed for the sidecar. |
| B8 | `frontend/vite.config.ts:18` | proxy target `http://localhost:8000` | Dev-only. Delete in 3.2. |
| B9 | `frontend/src/lib/api.ts:8` | `const BASE = "/api"` | KEEP. Relative is exactly right once same-origin. Verify it stays relative. |
| B10 | `.freebuff/stream-probe.py:14` | `http://127.0.0.1:8000/api/ask` | KEEP. Agent scratch, gitignored. |

### C. Model and asset identifiers

| # | Location | Value | Action |
|---|---|---|---|
| C1 | `config.py:50` | `OLLAMA_MODEL_NAME = "llama3:8b"` | Becomes the default only. App lets the user pick 3B or 8B; store the choice in a settings file. |
| C2 | `dev.py:53-56` | `MODEL = config.OLLAMA_MODEL_NAME` with `except: MODEL = "llama3:8b"` | The fallback literal re-introduces the duplicate. Drop the fallback; a missing config is a hard error. |
| C3 | `server.py:222` | error text `` `ollama run llama3:8b` `` | Hardcoded in a string. Interpolate `config.OLLAMA_MODEL_NAME`. |
| C4 | `server.py:278` | same string | Same fix. |
| C5 | `server.py:290` | same string | Same fix. |
| C6 | `config.py:47` | `EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"` | KEEP. Do not change; `config.py:42-46` records why bge lost. |
| C7 | `config.py:98` | `RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"` | KEEP. Needed at runtime, 88 MB. Must be bundled. |
| C8 | `config.py:49` | `WHISPER_MODEL = "small"` | Only needed to ingest NEW videos. Exclude from the shipped build (2.4). |
| C9 | `config.py:63-66` | `YOUTUBE_URLS` per profile | KEEP. Data. Only `og` lacks a URL. |
| C10 | `config.py:73-110` | `TOP_K_CHUNKS`, `RETRIEVE_K`, `RERANK_TOP_K`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, thresholds | KEEP. Retrieval tuning, out of scope for packaging. |

### D. Build and runtime assumptions

| # | Location | Issue | Action |
|---|---|---|---|
| D1 | machine | Python 3.14.7 in `%APPDATA%\Roaming\Python\Python314\site-packages`, no venv | App must own its interpreter. Freeze on 3.12 (2.1). |
| D2 | `requirements.txt` | `torch>=2.0`, `numpy>=1.24`, `transformers>=4.40`, others unpinned | Pin exact versions before freezing. An unpinned float is unreproducible. |
| D3 | `dev.py:50`, `server.py:24` | `sys.path.insert(0, ROOT)` | Assumes flat layout. Keep, but the frozen entry point must set this up itself. |
| D4 | `rag_chat.py:3-6`, `server.py:11-14` | `HF_HUB_OFFLINE=1` et al. set in code | KEEP, but add `HF_HOME` pointing at the bundled model dir so offline load finds it. |
| D5 | repo | No lockfile | Add one in 0.3. |
| D6 | `frontend/dist` | Exists locally (2.3 MB) but is **NOT tracked** — `frontend/.gitignore:11` excludes `dist`. `git ls-files frontend/dist` returns 0 files. | The directory must be produced by `cd frontend && npm run build` before any packaging step. The frozen sidecar in Batch 2 needs it; a fresh clone does not have it. |

### E. Runtime data that must ship

| Path | Size | Needed at runtime? |
|---|---|---|
| `faiss_index.bin` (og) | 2.0 MB | yes |
| `metadata.pkl` (og) | 1.3 MB | yes |
| `profiles/quantum/{faiss_index.bin,metadata.pkl}` | 0.2 + 0.1 MB | yes |
| `profiles/hades_demo/{faiss_index.bin,metadata.pkl}` | 0.9 + 0.4 MB | yes |
| `chunks/` | 1.37 MB / **1329 files** | **NO.** Runtime reads only `METADATA_PATH` (`rag_chat.py:42,103`). Every chunk's text is already inside `metadata.pkl` (`create_embeddings.py:53`). Only `retrieve.py:43` reads the `.txt` files, and that is a dev CLI. Exclude. |
| `profiles/hades_demo/chunks/` | 0.43 MB / **612 files** | **NO.** Same reason. Exclude. |
| `profiles/quantum/chunks/` | 0.10 MB / **139 files** | **NO.** Same reason. Exclude. |
| `profiles/*/transcripts/*_segments.json` | ~0.8 MB | yes, only for `chapters.json`-style tooling |
| `transcripts/`, `whisper/`, `video/`, `audios/` | large / gitignored | **no** — ingest only |

### F. Measured sizes (for the installer budget)

torch 453.4 MB · transformers 87.8 MB · numpy 30.3 MB · faiss 25.2 MB · sentence_transformers 4.0 MB
MiniLM 175 MB · reranker 88 MB · frontend 2.3 MB · indexes+data ~15 MB
→ **backend bundle ≈ 880 MB**, before the LLM.

---

### G. Hardcoding missed by the first sweep

Sweep 1 only read `.py/.ts/.tsx/.js/.json/.html` with packaging-shaped patterns. Sweep 2 opened the
four scripts sweep 1 never read and greped the prompt literals. These were missed. A third pass
(complete tracked-file list, the docs, and the built `frontend/dist/`) closed the last gap; G20-G22
come from it.

| # | Location | Value | Verdict |
|---|---|---|---|
| G1 | `transcribe_parts.py:7-10` | **four** `C:/Users/kingh/anaconda3/Lib/site-packages/nvidia/{cublas,cudnn,cuda_nvrtc,cuda_runtime}/bin` DLL dirs | **CRITICAL, same class as A1.** Guarded by `os.path.exists`, so it is silent not crashing — it just never adds the DLLs on another machine, and GPU transcription fails back to CPU. Ingest-only, so it never ships, but it is the second copy of a hardcoded username. Find them from `sys.prefix`/`site-packages` or drop the block. |
| G2 | `transcribe_parts.py:49` | comment "try GPU first (RTX 4050)" | Cosmetic. The 4-step device fallback chain below it is real and correct. KEEP the code, fix the comment. |
| G3 | `sum.py:1-3` | a **tracked** 3-line scratch file; `torch.cuda.get_device_name(0)` raises on any CPU-only machine | Delete the file. It is committed noise that crashes. |
| G4 | `download_hades_demo.py:5` | `url = "https://youtu.be/ygXn5nV5qFc"` | **Duplicate of `config.py:56`** `YOUTUBE_URLS["hades_demo"]`. Two sources, already driftable. Read from config. |
| G5 | `download_hades_demo.py:6` | `hades_demo.%(ext)s` | Filename literal. Derive from the profile name. |
| G6 | `download_hades_demo.py:12` | `height<=720` format selector | KEEP. Deliberate size/quality tradeoff, dev tool. |
| G7 | `checkup_timestamps.py:32-47` | `TOPICS` = 12 quantum + 14 hades_demo topic lists | KEEP as data, but this file is **dev-only** and must never be bundled. |
| G8 | `checkup_timestamps.py:49-81` | `TOPIC_CHAPTER` hand-asserted ground truth, including chapter titles like `"1.1 Introduction to Qubit"` | KEEP. It is the audit's ground truth and the reason the audit is trustworthy. Dev-only. |
| G9 | `checkup_timestamps.py:29` | `NEAR_SEC = 60` | KEEP. Documented tolerance for loose hand-authored chapter markers. |
| G10 | `chunk_transcripts.py:13-14` | `if args.profile == "hades_demo":` chunk size/overlap branch | Decide: per-profile values belong in `config.py` next to the other profile data, not in an `if`. |
| G11 | `chunk_transcripts.py:134-136` | `~750 chars/min` speech-rate estimate | KEEP as a fallback constant, but name it and move it to config. |
| G12 | `config.py:20` | `DEFAULT_PROFILE = "og"` while `YOUTUBE_URLS` (`config.py:55-58`) has **no `"og"` key** | **PRODUCT BUG.** First run defaults to the one profile whose timestamps cannot be clicked. Either default to `hades_demo`, or add the `og` URL. Decide in 0.10. |
| G13 | `retrieve.py:43` | reads `config.CHUNKS_DIR` `.txt` as a fallback | Dev CLI. KEEP, but it is the only reason `chunks/` looks needed. |
| G14 | `whisper/` | a **vendored whisper.cpp git repo, 82 files, with its own `.git`**, ignored at `.gitignore:27` | On disk, never ships, but any naive `copy .` or `PyInstaller --add-data .` drags it in. Add it to the packaging exclude list explicitly. |
| G15 | `video/`, `audios/`, `study.md` | gitignored (`.gitignore`), `video/` and `audios/` currently empty | Exclude. `download_hades_demo.py` would put a 1.2 GB mp4 in `video/`. |
| G16 | `server.py:107`, `:254`, `:286` | three prompt literals: the system persona `"You are HadeS, a knowledgeable and friendly teaching assistant"`, the 3-MCQ quiz prompt, and the 3-bullet summary prompt | KEEP behaviour, but prompts living inline in route handlers are untunable. Move all three to one place. |
| G17 | `rag_chat.py:390,392` | **the curator prompt hardcodes `02:06-02:10`, `02:28`, `03:48` and Python examples** (`"dog breed error"`, `"methods are functions"`, `"CSV file"`) | **CRITICAL for `quantum`.** The curator is asked to pick teaching moments using examples from the Python course. On the quantum profile those examples are meaningless and bias the pick. Make the prompt per-profile, or delete the example sentence. |
| G18 | `rag_chat.py:390` | same prompt: `"TEACH = definition + syntax + rules + how/why, with code example"` (the `e.g. "Defining functions", "What is a variable"` on the same line is G17) | Code-shaped definition of teaching. Wrong for a physics lecture. Same fix as G17. |
| G19 | `tests/test_retrieval.py:93-101` | the `__main__` block calls **8** of the **9** tests in the file. `test_confidence_includes_retrieved_pool` (`:38`) is never called. The module docstring (`:3`) says `Run: python tests/test_retrieval.py`. | **A test that never runs.** It is the regression test for the refusal gate ("the refusal gate must not flip with the curator's picks", `:39-40`). Running the documented command prints `all retrieval checks passed` while skipping it. `python -m pytest tests/` does run all 9. Measured: pytest `9 passed`, the script prints `all retrieval checks passed` — exit 0 both ways, so nothing surfaces the gap. |
| G20 | `README.md:78`, `NOTES.md:18-19`, `frontend-ideas/hades-rag-frontend-prompt.md:80` | run instructions naming the author's interpreter: "Anaconda base env is what this is tested on", `/c/Users/kingh/anaconda3/python.exe` | Docs only, nothing ships from them, but they are the copy a second developer follows. Rewrite to `python dev.py`; Batch 1's in-app guide is the real replacement. |
| G21 | `dev.py:597` | `_kill_tree(web_proc, port=5173)` — the first candidate literal, not the port Vite actually bound | Guarded by `_owner_is_ours()`, so it cannot kill a stranger; the failure mode is leaving our own Vite alive when the tree kill misses. Pass the detected port. Folded into Task 0.4. |
| G22 | `checkup_timestamps.py`, `chapters.json`, `TIMESTAMP_AUDIT.md` | all three are **untracked** (`git status` → `??`): the audit tool, its ground truth, and its report exist only on this disk | Decide once: commit them (the audit then reproduces from a clean clone and `git log` can date ground-truth changes) or keep them local (then the timestamp audit is a local-only guarantee). Either way keep them on the packaging exclude list (0.11). |

### H. Dead code and per-query waste

Not hardcoded, but it is what makes the app slow and the bundle big. Every caller count, import
count and size below was measured on this repo — the font and chunk rows also against the built
`frontend/dist/` on disk, not estimated. One thing checked that turned out fine: the scripted mocks
do **not** ship (`api.ts:7` is `USE_MOCK = import.meta.env.VITE_USE_MOCK === "1"`, statically false;
none of `mock-answers`' prose appears in the built chunk).

| # | Finding | Evidence | Cost |
|---|---|---|---|
| H1 | **A second full LLM generation per question.** `server.py:180` calls `search_chunks_curated(question)` with the default `use_llm=True` (`rag_chat.py:421`), so every answer runs one Ollama generation to pick 2 chunks and then a second one to write the answer. | `rag_chat.py:434` gate; `checkup_timestamps.py --no-llm` exists precisely because someone already wanted to turn it off | On a CPU-only box this is likely the single largest latency term after the answer itself. Unmeasured — measure it in 0.8 before deciding. |
| H2 | **Grounding validation is computed and never read.** `server.py:226-228` builds `validation` into the SSE payload. `grep -rn validation frontend/src` returns **zero rows**. | one extra MiniLM batch over every claim + every cited lesson, per answer | Pure waste, or an unfinished UI feature. Decide in 0.7. |
| H3 | **Unreachable retrieval code.** `search_chunks_simple` (`rag_chat.py:490`) and `search_chunks_detailed` (`rag_chat.py:505`) have **zero callers** anywhere. The whole BM25 + RRF path is unreachable while `RETRIEVE_MODE="dense"` (`config.py:83`). | caller counts: 0, 0, and `_bm25_for_profile` reachable only from the hybrid branch | Dead weight to read and to test. `tests/test_retrieval.py` tests the BM25/RRF helpers, so the tests keep the dead code alive. |
| H4 | **2080 `.txt` files that no runtime code opens.** | `chunks/` 1329 + 612 + 139 | 1.9 MB, but file *count* is what makes an installer slow and triggers AV scanners. |
| H5 | **One dead font package, four live ones — corrected by measurement.** 5 are declared (`frontend/package.json:14-18`). `geist` is imported **nowhere** and emits **zero** files. The other four are each imported once (`frontend/src/index.css:4-7`) and **all four appear in `frontend/dist/assets`** — they are used, not dead. | `grep -rn geist frontend/src` → 0 hits; `ls frontend/dist/assets \| grep -ci geist` → 0 | Delete `geist` only. Optional: import `/latin.css` subsets to stop emitting ~170 KB of cyrillic/greek/vietnamese faces the browser never fetches — build/install size, not runtime. See Task 0.12. |
| H6 | **Everything is one 1.75 MB chunk, three.js included.** Measured: `frontend/dist/assets/index-D0VvpeL7.js` = **1,836,798 bytes**, CSS 92,288 bytes, one request for the whole app. `three`, `@react-three/fiber` and `@react-three/drei` are imported by **exactly one file**, `ui/globe-hero.tsx:3-6`, used by exactly one component, `Landing.tsx:4,29`. `gsap` by exactly one file, `CinematicFooter.tsx:5`. | `ls -laS frontend/dist/assets`; import grep per file; the other two "three" hits (`About.tsx:364`, `mock-answers.ts:22`) are the English word | Lazy-load the landing scene so three.js moves to its own async chunk — Task 0.12 records the before/after delta. |
| H7 | Four overlapping UI-kit deps: `shadcn`, `cn`, `class-variance-authority`, `@base-ui/react`. | `frontend/package.json` | Audit later; not a packaging blocker. |

---

## Review Focus

Inputs and conditions this plan implies but whose tests nobody writes. Each is pinned to a task.

1. **Port 11434 already in use by something that is not Ollama.** `GET /api/version` returns
   non-JSON or a wrong shape. The app must say "something else is using this port", not crash.
   → test in 1.5.
2. **Ollama installed but stopped, and the exe is in neither known path** (user installed with
   `/DIR=`). Detection must report "not installed" honestly rather than silently hanging. → 1.1.
3. **A model is present whose name is a prefix match but not the configured one** (`llama3:latest`
   vs `llama3:8b`). `dev.py` already uses `startswith`; this over-matches. Decide and test. → 1.5.
4. **Disk fills during a pull.** Stream must surface the failure and leave state resumable. → 1.2.
5. **Install path contains a space or non-ASCII characters** (`C:\Program Files\...`). Every path
   join and every subprocess argument must survive it. → 2.5.
6. **Read-only install directory.** The app must keep writable state (settings, pulled-model
   bookkeeping) outside the install dir. → 2.3.
7. **Second launch while the first instance is running.** Two sidecars, two windows, one port.
   → 3.3.
8. **No GPU.** CPU inference is slow and the keep-alive is 6h. First-token latency must be
   communicated in the UI, not left as a hang. → 3.4.

---

## Batch 0 — Portability floor

No packaging. Makes the app run from any folder, on any machine, with one source of truth per value.
Entirely independent of Batch 1+. **Done when:** a second machine (or a different user profile) with
Ollama running gets a correct answer, and `grep` for each removed literal returns nothing.

### Task 0.1: Resolve model directories portably

**Files:**
- Modify: `rag_chat.py:49-68` (`_local_snapshot`)
- Test: `tests/test_model_paths.py` (new)

**Interfaces:**
- Produces: `rag_chat._model_search_roots() -> list[pathlib.Path]`, ordered:
  `$HADES_MODEL_DIR/env`, then `./models` next to the app, then `~/.cache/huggingface/hub`.
- Consumes: `config.EMBEDDING_MODEL_NAME`

- [x] **Step 1: Write the failing test**

```python
def test_search_roots_have_no_absolute_user_path(monkeypatch):
    monkeypatch.delenv("HADES_MODEL_DIR", raising=False)
    roots = rag_chat._model_search_roots()
    assert all("kingh" not in str(p) for p in roots)
    assert any(".cache/huggingface/hub" in str(p) for p in roots)

def test_env_dir_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("HADES_MODEL_DIR", str(tmp_path))
    assert rag_chat._model_search_roots()[0] == tmp_path
```

- [x] **Step 2: Run to verify it fails**

Run: `python tests/test_model_paths.py`
Expected: FAIL, `_model_search_roots` does not exist.

- [x] **Step 3: Implement `_model_search_roots()` and use it in `_local_snapshot`**

Delete the literal A1 root. Iterate the returned list in order. Keep the existing snapshot-picking
logic unchanged.

- [x] **Step 4: Verify it passes and load still works**

Run: `python tests/test_model_paths.py` → PASS
Run: `python -c "import rag_chat; rag_chat.set_profile('quantum'); print(rag_chat.get_model() is not None)"` → `True`

- [x] **Step 5: Commit**

```bash
git add rag_chat.py tests/test_model_paths.py
git commit -m "fix: resolve model dirs from env and app dir, drop hardcoded user path"
```

### Task 0.2: One source of truth for Ollama host and model name

**Files:**
- Modify: `config.py:50-51`, `dev.py:44-56`, `server.py:222,278,290`
- Note: `dev.py:53-56` is the MODEL block; `dev.py:50` is the `sys.path.insert`
- Test: `tests/test_config_single_source.py` (new)

**Interfaces:**
- Produces: `config.OLLAMA_HOST` (default `http://127.0.0.1:11434`),
  `config.OLLAMA_API_URL = f"{config.OLLAMA_HOST}/api/generate"`,
  `config.OLLAMA_TAGS_URL = f"{config.OLLAMA_HOST}/api/tags"`.
- Both env-overridable via `OLLAMA_HOST`.

- [x] **Step 1: Write the failing test**

```python
def test_no_duplicate_model_literal_outside_config_and_tests():
    import pathlib, re
    hits = []
    for p in pathlib.Path(".").glob("*.py"):
        if p.name in {"config.py", "checkup_timestamps.py"} or p.name.startswith("test_"):
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "llama3:8b" in line:
                hits.append(f"{p}:{i}")
    assert hits == [], f"duplicate model literal: {hits}"

def test_tags_url_derives_from_host(monkeypatch):
    import importlib, config
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:9999")
    importlib.reload(config)
    assert config.OLLAMA_TAGS_URL == "http://127.0.0.1:9999/api/tags"
```

- [x] **Step 2: Run to verify it fails**

Expected: FAIL, lists `dev.py` and three `server.py` lines.

- [x] **Step 3: Implement**

Add the derived constants in `config.py`. Fix all four call sites to interpolate
`config.OLLAMA_MODEL_NAME`. Delete the `dev.py` fallback literal (C2) — make a missing config raise.

- [x] **Step 4: Verify**

Run: `python tests/test_config_single_source.py` → PASS
Run: `python dev.py --help` → still parses
Run: `python -c "import server"` → imports clean

- [x] **Step 5: Commit**

```bash
git add config.py dev.py server.py tests/test_config_single_source.py
git commit -m "refactor: single source of truth for ollama host and model name"
```

### Task 0.3: Pin dependencies

**Files:**
- Modify: `requirements.txt`
- Create: `requirements.lock.txt`

- [x] **Step 1: Capture exact installed versions**

Run: `python -m pip freeze | grep -iE "^(torch|transformers|numpy|faiss|sentence|faster|fastapi|uvicorn|huggingface|requests)"`
Record the output verbatim.

- [x] **Step 2: Pin `requirements.txt` to those exact versions**

Use `==` for `torch` and `numpy` at minimum; those two cause the most silent drift.

- [x] **Step 3: Verify a fresh resolve is reproducible**

Run: `python -m pip install --dry-run -r requirements.txt`
Expected: reports already-satisfied, no upgrades.

- [x] **Step 4: Commit**

```bash
git add requirements.txt requirements.lock.txt
git commit -m "chore: pin dependency versions for reproducible builds"
```

### Task 0.4: Env-overridable port, host, and CORS

**Files:**
- Modify: `server.py:32-39`, `server.py:300`, `dev.py:597`
- Test: `tests/test_server_config.py` (new)

- [x] **Step 1: Write the failing test**

```python
def test_cors_origins_from_env(monkeypatch):
    monkeypatch.setenv("HADES_CORS_ORIGINS", "http://127.0.0.1:1234")
    import importlib, server
    importlib.reload(server)
    assert server.ALLOWED_ORIGINS == ["http://127.0.0.1:1234"]
```

- [x] **Step 2: Run to verify it fails**

Expected: FAIL, `ALLOWED_ORIGINS` not defined.

- [x] **Step 3: Implement**

`ALLOWED_ORIGINS` reads `HADES_CORS_ORIGINS` (comma-separated), defaulting to today's four values.
`uvicorn.run` reads `HADES_HOST` / `HADES_PORT`, `HADES_PORT=0` meaning "pick a free port and
print it to stdout on one line" so the shell can parse it.

While here, fix G21: `dev.py:597` passes the literal `port=5173` to `_kill_tree` as the cleanup
fallback — pass the port Vite actually bound (the detected `vite_url`) instead.

- [x] **Step 4: Verify**

Run: `python tests/test_server_config.py` → PASS
Run: `HADES_PORT=8011 python server.py` then `curl -s 127.0.0.1:8011/api/health` → JSON

- [x] **Step 5: Commit**

```bash
git add server.py dev.py tests/test_server_config.py
git commit -m "feat: read host, port and cors origins from environment; fix cleanup fallback port"
```

**Batch 0 gate:** all four tasks committed, `python dev.py` still boots the app end to end, and the
two grep checks (0.2 step 1, 0.1 step 1) pass.

---

## Batch 0.5 — Cut the dead weight and the dead second

From sections G and H. Still no user-visible feature work, and still no new dependencies. Depends
on Batch 0 only, and is **independent** of Batch 1 in principle — but do it before Batch 1, because 0.7 and 0.8
change the latency of the endpoint Batch 1 is about to build a UI around.

**Done when:** the bundle contains no `chunks/`, no `whisper/`, no ingest scripts, and no
`validate_grounding` call unless a config flag is on; and the curator decision is written down with
a measured number next to it, not an opinion.

### Task 0.5: Kill the remaining machine-specific paths and the scratch file

**Files:** Modify `transcribe_parts.py`, `download_hades_demo.py`, `chunk_transcripts.py`; delete `sum.py`

- [x] **Step 1: Add `kingh` to the grep gate from 0.1.** The existing check greps for the username;
  extend it to cover `transcribe_parts.py:7-10` so G1 cannot regress. Run it, watch it fail on the
  anaconda paths.
- [x] **Step 2: Replace the four anaconda DLL dirs** with paths derived from the interpreter that is
  actually running (`sys.prefix`, or `importlib.util.find_spec("nvidia")`). Keep the
  `os.path.exists` guard.
- [x] **Step 3: Point `download_hades_demo.py:5` at `config.YOUTUBE_URLS`** so G4 stops duplicating
  `config.py:56`. Derive the output filename from the profile (G5).
- [x] **Step 4: Delete `sum.py`** and record the deletion in the commit message.
- [x] **Step 5: Verify** — grep gate passes; `python transcribe_parts.py --help` still runs.
- [x] **Step 6: Commit**

### Task 0.6: Make the curator prompt profile-aware

**Files:** Modify `rag_chat.py:383-392`; Test: `tests/test_curator_prompt.py` (new)

- [x] **Step 1: Write the failing test.** Assert that the prompt built for profile `quantum`
  contains neither `"02:06"` nor `"dog breed"`, and that the prompt for `hades_demo` still does.
- [x] **Step 2: Run it** → FAIL.
- [x] **Step 3: Fix.** Move the example sentences on `rag_chat.py:390` and `:392` out of the f-string
  into a per-profile value in `config.py`, and drop the code-shaped definition of TEACH (G18) to
  something domain-neutral:
  "the segment where the teacher introduces and explains the topic".
- [x] **Step 4: Re-run `checkup_timestamps.py --profile quantum --no-llm`** and confirm the
  off-target count in `TIMESTAMP_AUDIT.md` does not get worse. It must not silently change here:
  this task is prompt hygiene, and if the number moves, that is a separate finding to record.
- [x] **Step 5: Commit**

### Task 0.7: Decide the fate of `validation`, then stop paying for it

**Files:** Modify `server.py:226-228`; Test: `tests/test_ask_payload.py` (new)

- [x] **Step 1: ANSWERED — it was never meant to render.** Searched the full history (repo has 11
  commits, so this is all of it): `git log -S"validation" -- frontend/` returns **0 commits**, and
  the only commit that introduces it at all is `b5c17ed feat: rerank retrieval and refuse
  unanswerable questions`, which is server-side. So `validation` was born as a server-side field and
  no frontend version ever consumed it. It is not a half-finished feature; it is unwired output.
  Re-check this if the frontend is ever branched from a different history.
- [x] **Step 2: DECIDED (user, this session).** Nothing renders it, and a low score sitting
  next to a good answer is a liability in front of judges — it must not ship in the answer path.
  Gated off rather than deleted: the function is still wanted for audit work.
- [x] **Step 3: Done.** `config.GROUNDING_VALIDATION = False`. The call site in `server.py` was
  already written as `getattr(config, "GROUNDING_VALIDATION", False)`, so this needed no code
  change there — only the default and the test.
- [x] **Step 4: Done.** `tests/test_ask_payload.py` — 3 tests: shipped default is off; flag off ⇒
  no `validation` key AND `validate_grounding` never called; flag on ⇒ the key and the call return.
- [x] **Step 5: Measured.** Same question (`what are functions`, `hades_demo`), same machine:
  validation ON `response_time` **24.9 s**, OFF **27.6 s**. One sample each and LLM-dominated, so
  the timing delta is inside run-to-run noise — this is a correctness/liability fix more than a
  speed fix, and the removed work is one MiniLM batch over claims + cited lessons.
- [x] **Step 6: Committed.**

### Task 0.8: Measure the curator before keeping it

**Files:** Modify `config.py`, `rag_chat.py:421,434`, `server.py:180`

The curator is a second Ollama generation per question (`rag_chat.py:434`, default `use_llm=True`),
and the A+B `_teaching_score` heuristic already produces a ranking on its own (`rag_chat.py:436` else-branch).
Nobody has measured whether the LLM pick is better than that heuristic — `config.py:79-96` measures
BM25, RRF and rerank, but not the curator.

- [x] **Step 1: Done.** `config.LLM_CURATOR_ENABLED` added. `server.py` passes it through
  explicitly with `functools.partial(..., use_llm=...)` instead of relying on the function default.
  Note it never shipped as `True`: the numbers below arrived before the first commit.
- [x] **Step 2: Measured** (`.freebuff/curator_bench.py`, llama3:8b already warm, hades_demo):

  | question | curator ON | curator OFF |
  |---|---|---|
  | what are functions | 2.37 s | 1.26 s |
  | what is a virtual environment | 1.24 s | 1.06 s |
  | what are strings in python | 4.23 s | 1.11 s |
  | **mean** | **2.62 s** | **1.14 s** |

  Delta **+1.47 s per question**, and the main-lesson pick was **identical in all three cases**.
- [x] **Step 3: Quality already measured — `TIMESTAMP_AUDIT.md` ran both curators over 152
  retrieval runs.** First-MAIN hits: hades_demo 7/8/7 (heuristic) vs 7/8/7 (LLM) — a wash; quantum
  `ask` **8/10 vs 7/10** — the heuristic is better; the audit's own read is that the LLM curator
  "flattens the quantum gap". Re-running those sweeps here would re-derive a number already in the
  repo, so the existing sweep is used and cited instead.
- [x] **Step 4: DECIDED — default OFF.** Same quality (identical picks in the sample; static sweeps a
  wash or favourably to the heuristic), a full extra generation of latency removed, and the flag
  stays for anyone who wants the LLM pick back. Written into "Decisions locked".
- [x] **Step 5: Committed.**

### Task 0.9: Delete the unreachable retrieval code

**Files:** Modify `rag_chat.py` (lines 490-537 and the BM25/RRF path), `tests/test_retrieval.py`

- [x] **Step 1: Confirm the zero-caller result yourself** before deleting: grep each symbol across
  the repo and record the counts in the commit message.
- [x] **Step 2: Decide per symbol.** `search_chunks_simple` and `search_chunks_detailed` (0 callers)
  go. The BM25/RRF path is a documented, deliberate opt-in for the reranker work (`config.py:79-83`)
  — keep it, but it needs a test that it still runs, since it is currently only kept alive by tests
  of its own helpers.
- [x] **Step 3: Delete, re-run `pytest tests/`, and expect the count to be UNCHANGED.** Measured
  baseline before touching anything: `python -m pytest tests/ -q` → **9 passed** in 0.61s. Neither
  `search_chunks_simple` nor `search_chunks_detailed` has a test, so a drop in that number means you
  deleted something live. The unchanged 9 is the proof they were dead.
- [x] **Step 3b: Fix the orphaned test (G19)** — add `test_confidence_includes_retrieved_pool()` to
  the `__main__` block at `tests/test_retrieval.py:93-101`, or delete the `__main__` block entirely
  and make the docstring say `python -m pytest tests/`. Prefer the second: a second hand-maintained
  runner is what created the gap. Do not delete the test itself.
- [x] **Step 4: Commit**

**Execution note:** the suite went 25 → 27 rather than staying flat. The flat count was the proof
that nothing live was deleted — deletion dropped no test, and the two-test rise is the new
`tests/test_hybrid_path.py` that exercises the hybrid dispatch through fakes.

### Task 0.10: Fix the default profile

**Files:** Modify `config.py:20`; Test: `tests/test_config.py` (new)

- [x] **Step 1: Write the failing test** — assert `DEFAULT_PROFILE in config.YOUTUBE_URLS`, with a
  comment saying why: a default profile without a URL gives the user timestamps that cannot be clicked.
- [x] **Step 2: Run it** → FAIL (G12).
- [x] **Step 3: Fix** — either default to `hades_demo`, or add an `og` URL. Pick one and record why
  in the config comment. Do not do both.
- [x] **Step 4: Commit**

### Task 0.11: The packaging exclude list

**Files:** Create `packaging/exclude.txt`; record in this plan

Nothing may be bundled by accident. Write the list down once and reference it from Batch 2.

- [x] **Step 1: Write the list:** `whisper/` (G14), `video/`, `audios/`, `chunks/`,
  `profiles/*/chunks/`, `transcripts/`, `profiles/*/transcripts/`, `checkup_timestamps.py`,
  `chunk_transcripts.py`, `create_embeddings.py`, `transcribe_parts.py`, `process_video.py`,
  `download_hades_demo.py`, `.freebuff/`, `docs/`, `onepager/`, `frontend-ideas/`, `tests/`.
- [ ] **Step 2: Verify by size, not by trust** — after Batch 2's freeze, list the bundle contents and
  grep the list for each excluded name. Report the count of matches, which must be 0.
- [x] **Step 3: Commit**

### Task 0.12: Shrink the first-load payload

**Files:** Modify `frontend/package.json`, `frontend/src/components/ui/globe-hero.tsx`; Create
`frontend/src/components/ui/globe-scene.tsx`
**Measured baseline:** `frontend/dist/assets/index-D0VvpeL7.js` = **1,836,798 bytes** (one chunk,
three.js included), `index-C0464ae5.css` = 92,288 bytes, 20 font files (build on disk, Oct 9).
This task records the delta; the absolute number below is provenance, not a target.

- [x] **Step 0: Baseline rebuilt on this machine.** `dist/assets/index-D0VvpeL7.js` =
  **1,836,798 bytes** (one chunk, three.js inside), `index-C0464ae5.css` = 92,288, 20 font files,
  `ls dist/assets | grep -ci geist` = **0** (H5 confirmed by measurement).
- [x] **Step 1: Done.** `@fontsource-variable/geist` removed with `npm uninstall` — zero import
  sites, zero emitted files. The other four font packages are each imported once (`index.css:4-7`)
  and stay.
- [x] **Step 2: Done, one level lower than this plan first said.** `DotGlobeHero` is the hero
  *container*, so lazying it would have delayed the hero text and CTAs along with the canvas. The
  three.js scene moved to a new `ui/globe-scene.tsx`; `globe-hero.tsx` imports it through
  `React.lazy` + `Suspense` (`fallback={null}` — the hero already paints its own backdrop).
  `Landing.tsx` is untouched.
- [x] **Step 3: Verified.** Main JS chunk **1,836,798 → 925,297 bytes (−49.6%)**; three.js now
  lives in its own `globe-scene-*.js` = **912,542 bytes**, fetched on demand. CSS unchanged at
  92,288. All three node checks print `ok`. The landing was opened in the browser panel: the
  wireframe globe renders, and the network log shows `three.js`, `@react-three/fiber` and `drei`
  arriving from the lazy chunk. The only failed requests were `/api/health` 502s while the backend
  was down — expected, and 200 once `python server.py` was started.
- [x] **Step 4: Numbers recorded above; committed.**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src
# frontend/src covers Landing.tsx plus any new lazy-wrapper file
```

**Batch 0.5 gate:** the grep gate passes, `pytest tests/` is green, the three node checks are green,
the curator and validation numbers are written down, the frontend main chunk is smaller than its
Step 0 baseline with three.js in a separate chunk, and `python dev.py` still answers a question end
to end.

**Batch 0.5 gate status: PASSED on this machine.** `pytest tests/` **33 passed**; the three node
checks print `ok`; main chunk **1,836,798 → 925,297** with `globe-scene-*.js` (912,542) separate;
`dev.py` boots the stack (`Ready.` at +17.4 s) and a live `/api/ask` still returns the correct main
lesson (`02:06:45 – 02:09:43`) in **24.0 s**, with no `validation` key in the payload. All eight
tasks committed.

---

## Batch 1 — Setup API and first-run guide

Ships real user value with no installer. Depends on Batch 0 for `config.OLLAMA_*`.
**Done when:** deleting the model (`ollama rm llama3:8b`) and relaunching lets you get back to a
working app using clicks only, and the status endpoint is covered by tests with fakes.

### Task 1.1: `/api/setup/status`

**Files:**
- Modify: `server.py` (add route near `/api/health`)
- Test: `tests/test_setup_status.py` (new)

**Interfaces:**
- Produces: `GET /api/setup/status -> {ollama_running: bool, ollama_installed: bool, version: str|None, model_present: bool, model_name: str, models: list[str]}`
- Consumes: `config.OLLAMA_TAGS_URL`, `dev.py`'s `_ollama_exe()` logic (lift it into a shared module)

- [x] **Step 1: Write the failing tests** — fake the HTTP call and the filesystem

```python
def test_not_installed(fake_no_ports, fake_no_exe):
    assert setup_status()["ollama_installed"] is False

def test_installed_but_stopped(fake_no_ports, fake_exe):
    s = setup_status()
    assert s["ollama_installed"] is True and s["ollama_running"] is False

def test_model_present_matches_configured_name(fake_tags_llama3_latest, fake_exe):
    # llama3:latest must NOT count as llama3:8b present
    assert setup_status()["model_present"] is False
```

- [x] **Step 2: Run to verify it fails**

Run: `python tests/test_setup_status.py` → FAIL

- [x] **Step 3: Implement**

Extract `_ollama_exe()` from `dev.py` into `ollama_locator.py` so `server.py` and `dev.py` share it.
Implement the four-boolean status. Resolve review-focus #3 here: exact tag match, not `startswith`.

- [x] **Step 4: Verify**

Run: `python tests/test_setup_status.py` → PASS
Run against the real machine: `curl -s 127.0.0.1:8000/api/setup/status` → `ollama_running: true`,
`model_present: true` for `llama3:8b`.

- [x] **Step 5: Commit**

```bash
git add server.py ollama_locator.py tests/test_setup_status.py
git commit -m "feat: setup status endpoint for first-run detection"
```

### Task 1.2: `POST /api/setup/pull` with progress stream

**Files:**
- Modify: `server.py`
- Test: `tests/test_setup_pull.py` (new)

**Interfaces:**
- Produces: SSE stream of `{"status": str, "completed": int|None, "total": int|None}` then `{"done": true}` or `{"error": str}`.
- Consumes: Ollama `POST /api/pull` with `stream: true`.

- [x] **Step 1: Write the failing test**

```python
def test_pull_emits_progress_then_done(fake_pull_stream):
    events = list(pull_events("llama3:8b"))
    assert events[0]["status"] == "pulling manifest"
    assert any(e.get("total") for e in events)
    assert events[-1]["done"] is True

def test_pull_error_is_surfaced_not_swallowed(fake_pull_error):
    events = list(pull_events("nope/x:1b"))
    assert "error" in events[-1]
```

- [x] **Step 2: Run to verify it fails** → FAIL

- [x] **Step 3: Implement** — proxy the upstream NDJSON, re-emit as SSE, never buffer the whole body.
  On upstream error emit `{"error": ...}` and end the stream.

- [x] **Step 4: Verify**

Run: `python tests/test_setup_pull.py` → PASS
Run: `curl -N -X POST 127.0.0.1:8000/api/setup/pull -d '{"model":"nope/x:1b"}'` → ends with an error event, no hang.

- [x] **Step 5: Commit**

```bash
git add server.py tests/test_setup_pull.py
git commit -m "feat: stream model download progress to the client"
```

### Task 1.3: Start a stopped Ollama

**Files:** Modify `server.py`, `ollama_locator.py`

- [x] **Step 1: Test that starting an already-running Ollama is a no-op**

```python
def test_start_is_idempotent_when_running(fake_running_tags):
    assert start_ollama()["started"] is False
```

- [x] **Step 2: Run to verify it fails** → FAIL

- [x] **Step 3: Implement** — reuse `dev.py`'s spawn-and-poll approach: spawn `ollama serve`
  detached, poll `/api/tags` with a bounded timeout, return `{started: bool, error: str|None}`.

- [x] **Step 4: Verify** — stop Ollama from the tray, call the endpoint, confirm it comes up.
  Run: `python tests/test_setup_pull.py` → still PASS

- [x] **Step 5: Commit**

```bash
git add server.py ollama_locator.py
git commit -m "feat: start ollama on demand from the app"
```

### Task 1.4: First-run screen

**Files:**
- Create: `frontend/src/components/SetupGuide.tsx`
- Create: `frontend/src/components/SetupGuide.css` (or Tailwind classes, matching existing style)
- Modify: `frontend/src/App.tsx`, `frontend/src/lib/api.ts`

**Interfaces:**
- Consumes: `/api/setup/status`, `/api/setup/pull`, `/api/setup/start`
- Produces: nothing other components depend on; it gates the app behind a ready state.

- [x] **Step 1: Add API client functions** to `frontend/src/lib/api.ts`:
  `fetchSetupStatus()`, `pullModel(name, onProgress)`, `startOllama()`.

- [x] **Step 2: Build the three states** — not installed / installed but stopped / model missing.
  Not-installed shows the copy-paste line; the other two show a button.

- [x] **Step 3: Verify in the browser** — run `python dev.py`, tab away, `ollama rm llama3:8b`,
  reload, confirm the model-missing state and that the button reaches 100%.

- [x] **Step 4: Verify the not-installed state** with `HADES_OLLAMA_EXE=/nonexistent`.

- [x] **Step 5: Commit**

```bash
git add frontend/src/components/SetupGuide.tsx frontend/src/lib/api.ts frontend/src/App.tsx
git commit -m "feat: first-run setup guide for ollama and model download"
```

### Task 1.5: Re-check tests and port-in-use behaviour

**Files:** `tests/test_setup_status.py`

- [x] **Step 1: Add the failing test for review focus #1**

```python
def test_port_taken_by_foreign_service(fake_port_with_html):
    s = setup_status()
    assert s["ollama_running"] is False
    assert s["port_conflict"] is True
```

- [x] **Step 2: Run to verify it fails** → FAIL

- [x] **Step 3: Implement** the `port_conflict` field: a response that is not JSON, or JSON without
  `version`, means something else owns 11434.

- [x] **Step 4: Verify** → PASS

- [x] **Step 5: Commit**

```bash
git add server.py tests/test_setup_status.py
git commit -m "fix: report port conflicts instead of assuming ollama is down"
```

**Batch 1 gate:** all of Batch 1 committed; a user can go from no model to a working answer with
clicks only; the guide is reachable at first run.

**Batch 1 gate status: PASSED on this machine.** `/api/setup/status` reports installed /
running / model-present (exact tag match, port-conflict detection), `/api/setup/start` launches a
stopped Ollama, `/api/setup/pull` streams real download progress, and the first-run guide renders
its three-node flowchart in the browser in both the model-missing and not-installed states
(screenshots taken this session). 13 new tests, `pytest tests/` 52 passed, three node checks green.


---

## Batch 2 — Backend packaging

Depends on Batch 0 (clean paths). **Done when:** the frozen sidecar starts from a clean temp
directory with no Python installed, serves `/api/health`, and answers a question using a bundled
index and bundled models.

### Task 2.1: Choose and prove the freezer

**Files:** Create `packaging/backend.spec` (or `packaging/build.py`)

- [ ] **Step 1: Test PyInstaller on the pinned interpreter first**

Run: `python -m pip install pyinstaller` then `pyinstaller --version`
If it refuses the interpreter version, fall back to Nuitka. Record which one worked and why.

- [ ] **Step 2: Freeze a trivial FastAPI app** (one route) and confirm it runs

Run: `packaging/backend.exe` then curl the route.
This isolates "can we freeze at all" from "can we freeze torch".

- [ ] **Step 3: Freeze the real entry point** `packaging/entry.py`, which imports `server`
  and calls `uvicorn.run`. Add hidden imports for `faiss`, `sentence_transformers`,
  `torch`, `transformers` as the build tells you they are missing.

- [ ] **Step 4: Verify** `/api/health` and `/api/ask` respond from the frozen exe.

- [ ] **Step 5: Commit**

```bash
git add packaging/
git commit -m "build: freeze the fastapi backend into a single executable"
```

### Task 2.2: Bundle the models and point the app at them

**Files:** Modify `packaging/backend.spec`, `rag_chat.py` (only the roots list from 0.1)

- [ ] **Step 1: Test that a bundled model dir is found**

```python
def test_bundled_models_dir_is_used(monkeypatch, tmp_path):
    monkeypatch.setenv("HADES_MODEL_DIR", str(tmp_path))
    assert rag_chat._model_search_roots()[0] == tmp_path
```

- [ ] **Step 2: Run** → PASS already from 0.1. If it fails, fix 0.1 rather than adding a special case.

- [ ] **Step 3: Copy MiniLM and the reranker into `models/` and ship them.** Set `HF_HOME` to the
  bundled dir at sidecar start, before importing `rag_chat`.

- [ ] **Step 4: Verify offline** — disconnect the network, run the frozen exe, ask a question.
  Expected: an answer. Any hub DNS attempt means D4 was not applied.

- [ ] **Step 5: Commit**

```bash
git add packaging/ rag_chat.py
git commit -m "build: bundle embedding and reranker models, load fully offline"
```

### Task 2.3: Bundle the indexes and keep writes outside the install dir

**Files:** Modify `packaging/backend.spec`, `config.py`

- [ ] **Step 1: Test that writable state resolves outside the install dir**

```python
def test_state_dir_is_writable_and_outside_install():
    d = config.state_dir()
    assert d.exists() and os.access(d, os.W_OK)
```

- [ ] **Step 2: Run to verify it fails** → FAIL, `state_dir` missing

- [ ] **Step 3: Implement `config.state_dir()`** — `%LOCALAPPDATA%\HadeS` by default,
  overridable by `HADES_STATE_DIR`. Put settings here. Leave indexes read-only in the bundle.

- [ ] **Step 4: Verify** — set the install dir read-only and confirm the app still starts and
  stores settings successfully.

- [ ] **Step 5: Commit**

```bash
git add config.py packaging/
git commit -m "feat: keep writable state outside the install directory"
```

### Task 2.4: Drop the ingest-only dependencies from the shipped build

**Files:** Modify `packaging/backend.spec`, `requirements.txt`

- [ ] **Step 1: Confirm `faster-whisper` is unreachable from the server path**

Run: `python -c "import server, sys; print('faster_whisper' in sys.modules)"` → `False`

- [ ] **Step 2: Exclude `faster_whisper`, `whisper`, `transcribe_parts`, `download_hades_demo`,
  and `chunk_transcripts` from the bundle.** Saves 606 MB of whitespace models and the ffmpeg
  dependency.

- [ ] **Step 3: Verify** the frozen exe still answers a question and `/api/health` is green.

- [ ] **Step 4: Commit**

```bash
git add packaging/backend.spec requirements.txt
git commit -m "build: exclude transcription tooling from the shipped app"
```

### Task 2.5: Prove it runs from a hostile path

**Files:** Create `packaging/smoke.md` (the manual check, written down)

- [ ] **Step 1: Copy the bundle to `C:\Temp\HadeS Test Äpp\`** (space plus non-ASCII)
- [ ] **Step 2: Run it with no Python on PATH** and confirm `/api/health`
- [ ] **Step 3: Run it twice in a row** and confirm nothing is locked or left behind
- [ ] **Step 4: Record the final on-disk size** in `packaging/smoke.md`
- [ ] **Step 5: Commit**

```bash
git add packaging/smoke.md
git commit -m "docs: record packaging smoke results and final bundle size"
```

**Batch 2 gate:** frozen sidecar answers a question from a clean machine/path with no Python
installed, network off, and a size recorded under 1.5 GB.

---

## Batch 3 — Desktop shell

Depends on Batch 2. **Done when:** double-clicking one installer gives a window that reaches a
working answer with no terminal ever visible, and a second launch does not start a second backend.

### Task 3.1: Pick the shell

- [ ] **Step 1: Decide Tauri vs Electron.** Default Tauri: it reuses the system webview, which
  matters when the payload is already 880 MB. Only pick Electron if Tauri blocks on WebView2.
- [ ] **Step 2: Write the decision and the reason in this file under "Decisions locked".**
- [ ] **Step 3: Commit** the note.

### Task 3.2: Serve the UI from FastAPI and delete the proxy

**Files:** Modify `server.py`, delete `frontend/vite.config.ts` proxy block, delete the `server.py:32-39` CORS block

- [ ] **Step 0: Build the frontend** — `cd frontend && npm run build`. Required: `dist` is gitignored
  (`frontend/.gitignore:11`), so a fresh clone does not have it. Verified: **`server.py` has no static
  mount today** — grep for `StaticFiles|FileResponse|HTMLResponse|mount(` across all `*.py` returns
  nothing, and the UI is served by Vite with `/api` proxied to `:8000`
  (`frontend/vite.config.ts:15-21`). So this task adds the mount; it does not fix an existing one.

- [ ] **Step 1: Test that `/` serves the built index**

```python
def test_root_serves_frontend_index(client):
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
```

- [ ] **Step 2: Run to verify it fails** → FAIL

- [ ] **Step 3: Mount `frontend/dist`** with `StaticFiles`, keeping `/api/*` routed first. Fail loudly
  at startup if `dist/index.html` is missing, rather than serving a 404 later.
  Delete the CORS middleware and the Vite proxy. Same origin makes both unnecessary.

- [ ] **Step 4: Verify** — frozen exe, open `127.0.0.1:<port>/`, full ask flow works, and
  `frontend/src/lib/api.ts` still uses the relative `BASE`. Re-run the three node checks (they cover
  the quiz parsing, source-link and streaming contracts this task now serves) and record the chunk
  sizes next to Task 0.12's numbers — serving the build must not change what the build contains.

- [ ] **Step 5: Commit**

```bash
git add server.py frontend/vite.config.ts
git commit -m "feat: serve the built frontend from the api, drop proxy and cors"
```

### Task 3.3: Shell supervises the sidecar

- [ ] **Step 1: Test the second-launch case (review focus #7)** — a named mutex or a lockfile in
  `config.state_dir()`. Second instance focuses the existing window and exits.
- [ ] **Step 2: Implement** spawn sidecar on a free port, parse the port from its stdout, open the
  window, and kill the sidecar on window close.
- [ ] **Step 3: Verify** — launch twice; the second must not spawn a second backend.
- [ ] **Step 4: Commit**

### Task 3.4: First-run cold start with no GPU

- [ ] **Step 1: Measure** first-token latency with a cold Ollama on this CPU-only machine.
- [ ] **Step 2: Show a warm-up state** using the existing stage callbacks so the user sees
  "loading model" rather than an empty box.
- [ ] **Step 3: Verify** on a cold boot (Ollama not running) that the guide, the model load, and
  the first answer all complete without a terminal.
- [ ] **Step 4: Commit**

### Task 3.5: Measure and record the installer

- [ ] **Step 1: Build the installer**
- [ ] **Step 2: Record the size and the install time** in `packaging/smoke.md`
- [ ] **Step 3: Commit**

### Task 3.6: Brand the app — "Made by Kumar Harsh"

**Files:** Modify `desktop/tauri.conf.json` (or the Electron equivalent), `desktop/package.json`,
`frontend/src/components/SetupGuide.tsx`

Sites already credit the author in the web UI — `Sidebar.tsx:68` ("by Kumar Harsh · v2"),
`About.tsx:415` ("HadeS — by Kumar Harsh · v2"), `CinematicFooter.tsx:325` ("© 2026 Kumar Harsh").
The shell is what is missing, and it is the part the user sees before the UI paints.

- [ ] **Step 1: Window and taskbar identity** — window title `HadeS — Teaching Assistant`; app name
  `HadeS`; icon from the existing `frontend/public` favicon set (regenerate multi-size `.ico`/`.png`
  from the same source, do not draw a new one).
- [ ] **Step 2: Installer metadata** — publisher `Kumar Harsh`, copyright
  `© 2026 Kumar Harsh. MIT License.`, homepage `https://github.com/kumarharshzzz04/HadeS`,
  `productName: HadeS`, `identifier: dev.kumarharsh.hades`.
- [ ] **Step 3: An About panel** inside the shell (Tauri menu “About HadeS”, or a footer line in
  SetupGuide.tsx once setup is done): name, version, author, repo link, MIT notice.
- [ ] **Step 4: Verify** the built installer shows publisher `Kumar Harsh` (file properties →
  Details) and the About panel names the author; screenshot into `packaging/smoke.md`.
- [ ] **Step 5: Commit**

```bash
git add desktop/ frontend/src/components/SetupGuide.tsx
# frontend/dist if the setup-guide change is part of the served build
git commit -m "feat: brand the desktop app with author, version and license info"
```

**Batch 3 gate:** one installer, one double-click, one working answer, no terminal, and the size
written down.

---

## Batch 4 — Optional: zero-touch Ollama

Only if Batch 3 testing shows users still fail at the Ollama step. **Independent** of Batches 1-3.

- [ ] **Step 1: Decide.** Ship `ollama-windows-amd64.zip` inside the installer, or keep asking the
  user to run one line? The zip removes step 1 at the cost of hosting it and carrying the MIT notice.
- [ ] **Step 2: If bundling:** extract to `config.state_dir()/ollama`, set `OLLAMA_MODELS` to
  `config.state_dir()/models`, spawn `ollama serve`, poll `/api/tags`. Untested assumption from the
  research: `OLLAMA_MODELS` must be set before the server starts. Verify that first.
- [ ] **Step 3: Carry the Ollama MIT licence notice and any model-weight licences separately.**
- [ ] **Step 4: Verify on a machine with no Ollama installed at all.**
- [ ] **Step 5: Commit**

---

## Decisions locked

- Sidecar serves the UI. Kills CORS and the Vite proxy together.
- Ollama stays external through Batch 3.
- Model choice is the user's: 3B (~2 GB, fits 16 GB RAM) or 8B (~4.7 GB, needs 7-10 GB).
  Default shown is 3B with 8B offered, because the target machine is CPU-only.
- `faster-whisper` and all transcription tooling are excluded from the shipped app.
- Retrieval ranking is NOT changed by this plan. See `TIMESTAMP_AUDIT.md` for that work.
- Dead weight is excluded, never bundled (Task 0.11): 2080 chunk `.txt` files, the vendored
  `whisper/` repo, and every ingest script.
- The curator LLM call and the grounding check are both config-gated in Batch 0.5, and their fate is
  decided by a measurement, not a preference.
- The shipped artifact is a **Windows desktop app** (Batch 3 Task 3.6 brands it "Made by Kumar
  Harsh"). "APK" in conversation means this installer package, not an Android build — the phone is
  explicitly out of scope for this plan.
- The shipped UI is the **React build** from `frontend/dist`. There is no Streamlit app left in the
  repo to port; Streamlit survives only in v1 history and in three prompt comments.
- Grounding `validation` stays in the code but out of `/api/ask` payloads (Task 0.7).
- The curator LLM is **off by default** (Task 0.8): +1.47 s/question for a pick that was identical
  on all three sampled questions and no better than `_teaching_score` over the 152-run audit sweep.
  `_teaching_score` + the dense-top-1 prior is the shipped ranking.

## Open questions

- Does `OLLAMA_MODELS` apply when the Ollama tray app is already running? Untested.
- Can a pull be cancelled? Ollama documents no cancel endpoint. Treat pull as resumable.
- PyInstaller and Nuitka support for Python 3.14 is unverified. Task 2.1 settles it; if both fail,
  freeze on 3.12.
- ~~Is `validation` an unfinished feature or a permanent no-op?~~ **Answered:** unwired server-side
  output. `git log -S"validation" -- frontend/` → 0 commits across all 11; introduced server-side by
  `b5c17ed`. Only the removal decision (0.7 step 2) is still open, because it needs the user's call.
- Does the curator LLM beat the `_teaching_score` heuristic enough to justify a second generation on
  every question? Unmeasured. 0.8 measures it.
- Is `whisper/` load-bearing, or leftover? It is a full vendored repo with its own `.git` on the dev
  machine only. Nothing in the app imports it; the audio pipeline calls `faster-whisper`, not this.
  Treat as dead until proven otherwise, and do not delete it without asking — it is the user's.
