# server.py — HadeS API bridge
# =============================================================================
# Thin FastAPI layer over rag_chat.py (which stays 100% untouched).
#   python server.py        →  http://localhost:8000
# The Vite dev server already proxies /api → localhost:8000.
# =============================================================================
import os
# Same environment guarantees as rag_chat.py (offline + OpenMP fix),
# applied BEFORE any HF/faiss import happens through rag_chat.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import functools
import json
import pathlib
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import ollama_locator
import rag_chat

app = FastAPI(title="HadeS API", version="1.0")

# Dev-only origins. Same-origin serving (Batch 3.2) makes CORS unnecessary; until then the
# list is env-overridable so a packaged app or a relocated dev port is not blocked (B6).
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "HADES_CORS_ORIGINS",
        "http://localhost:5173,http://localhost:5174,"
        "http://127.0.0.1:5173,http://127.0.0.1:5174",
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

_executor = ThreadPoolExecutor(max_workers=2)


# ── request/response models ──────────────────────────────────────────────────

class AskRequest(BaseModel):
    question: str
    profile: Optional[str] = None
    history: list[dict] = []  # [{question, answer}] — last N turns (client-trimmed)


class QuizRequest(BaseModel):
    question: str
    context: str  # joined source texts for this message (client-built)


class SummaryRequest(BaseModel):
    questions: list[str]  # completed questions this session


# ── helpers ──────────────────────────────────────────────────────────────────

def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _warmup():
    """Best-effort preload of embeddings + index so the first question
    doesn't pay the model-load cost. Runs in a worker thread."""
    try:
        rag_chat.get_model()
        rag_chat.get_index()
        rag_chat.get_metadata()
    except Exception:
        pass  # a real request still reports load errors properly


def _warmup_llm():
    """Load the Ollama model while the app boots. Without this the first answer
    sits silent for 25-30s (model load) before the first token, which reads as a
    frozen backend. Own thread so it doesn't delay the embedding preload."""
    if getattr(config, "LLM_WARMUP_ENABLED", True):
        rag_chat.warmup_llm()


def _clean_detail(d: dict) -> dict:
    """SourceDetail for the frontend — drop the raw cluster payload."""
    return {
        "label": d.get("label", ""),
        "text": d.get("text", ""),
        "start": d.get("start"),
        "end": d.get("end"),
        "part": d.get("part", 0),
        "youtube_url": d.get("youtube_url"),
        "score": d.get("score"),
        "cluster_size": d.get("cluster_size", 1),
    }


def _build_prompt(question: str, context: str, history: list[dict]) -> str:
    """Verbatim prompt shape from the original Streamlit UI (CHT_HISTORY_TURNS=3, client-trimmed)."""
    hist = "\n".join(
        f"User: {h.get('question', '')}\nAssistant: {str(h.get('answer', ''))[:600]}"
        for h in history[-config.CHAT_HISTORY_TURNS:]
    ) if history else "(no prior conversation)"
    return f"""You are HadeS, a knowledgeable and friendly teaching assistant.

Answer the student's question using ONLY the lecture context below — don't invent facts beyond it. If the answer isn't in the context, say honestly: "I couldn't find this in your lecture transcripts — try rephrasing."

Be thorough and educational: use 2-4 bullet points or short paragraphs, include key definitions and concrete examples from the lectures.

Conversation history (for follow-ups):
{hist}

Lecture context:
{context}

Current question: {question}

Answer (clear, structured):"""


def _history_pairs(history: list[dict]) -> list[dict]:
    """Feed last-3-turn history into rag_chat.set? No — rag_chat is stateless
    about history; the UI injects it into the prompt. Same here."""
    return history


# ── endpoints ────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    ollama_ok = False
    try:
        r = requests.get(config.OLLAMA_TAGS_URL, timeout=2)
        ollama_ok = r.ok
    except Exception:
        pass
    return {"ok": True, "ollama": ollama_ok, "model": config.OLLAMA_MODEL_NAME}


@app.get("/api/profiles")
def profiles():
    out = []
    for p in rag_chat.list_profiles():
        out.append({"name": p["name"], "ready": p["ready"], "chunks": p["chunks"]})
    return out


# ── first-run setup (plan Batch 1) ───────────────────────────────────────────

class PullRequest(BaseModel):
    model: str = ""


class SelectModelRequest(BaseModel):
    model: str


@app.get("/api/setup/status")
def setup_status():
    """Installed? running? model present? — the three questions the guide needs."""
    s = ollama_locator.status()
    s["offered"] = [dict(m) for m in config.OFFERED_MODELS]
    return s


@app.post("/api/setup/start")
def setup_start():
    """Start a stopped Ollama (no-op when it is already answering)."""
    return ollama_locator.start()


@app.post("/api/setup/select")
def setup_select(req: SelectModelRequest):
    """Switch the model in place — effective now, remembered for the next launch."""
    model = req.model.strip()
    if not model:
        raise HTTPException(status_code=400, detail="Empty model name")
    config.OLLAMA_MODEL_NAME = model
    config.save_settings(model=model)
    return {"ok": True, "model": model}


@app.post("/api/setup/pull")
def setup_pull(req: PullRequest):
    """Stream a model download as SSE: status/completed/total, then done or error."""
    model = (req.model or config.OLLAMA_MODEL_NAME).strip()

    def events():
        yield _sse({"status": "starting", "completed": None, "total": None})
        ok = False
        try:
            for evt in ollama_locator.pull_events(model):
                if evt.get("done"):
                    ok = True
                yield _sse(evt)
        except Exception as e:  # noqa: BLE001
            yield _sse({"error": f"pull failed: {e}"})
            return
        if ok:
            # remember what was just downloaded so the next launch uses it
            config.OLLAMA_MODEL_NAME = model
            config.save_settings(model=model)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/profiles/{name}")
def switch_profile(name: str):
    try:
        rag_chat.set_profile(name)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown profile {name!r}")
    return {"ok": True, "profile": name}


@app.post("/api/ask")
def ask(req: AskRequest):
    if req.profile:
        try:
            rag_chat.set_profile(req.profile)
        except ValueError:
            raise HTTPException(status_code=404, detail=f"Unknown profile {req.profile!r}")

    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Empty question")

    def event_stream():
        t0 = time.time()
        yield _sse({"type": "stage", "stage": "searching"})

        try:
            # retrieval + A+B curation (embed + FAISS are sub-second; the
            # curation LLM call inside is the long pole). Run in a thread so
            # we can flip the stage to "solving" once we're past retrieval.
            # Curator on/off is explicit here (Task 0.8) — not an invisible default argument.
            fut = _executor.submit(
                functools.partial(
                    rag_chat.search_chunks_curated,
                    question,
                    use_llm=getattr(config, "LLM_CURATOR_ENABLED", True),
                )
            )
            solving_sent = False
            while not fut.done():
                time.sleep(0.1)
                if not solving_sent and time.time() - t0 > 1.2:
                    solving_sent = True
                    yield _sse({"type": "stage", "stage": "solving"})
            if not solving_sent:
                yield _sse({"type": "stage", "stage": "solving"})
            curated = fut.result()
        except FileNotFoundError as e:
            yield _sse({"type": "error", "message": f"{e} — run `python create_embeddings.py --profile {rag_chat._profile()}`"})
            return
        except Exception as e:  # noqa: BLE001
            yield _sse({"type": "error", "message": f"Retrieval failed: {e}"})
            return

        # Refuse before generation when retrieval found nothing relevant.
        confidence = rag_chat.curated_confidence(curated)
        if getattr(config, "REFUSAL_ENABLED", False) and confidence < getattr(config, "MIN_RETRIEVAL_CONFIDENCE", 0.0):
            yield _sse({
                "type": "final",
                "answer": "I couldn't find this in the indexed lectures. Try rephrasing, or check whether the topic is covered in the current dataset.",
                "curated": {"main": [], "also": []},
                "response_time": round(time.time() - t0, 1),
                "declined": True,
                "confidence": round(confidence, 3),
            })
            return

        yield _sse({"type": "stage", "stage": "composing"})

        context = curated.get("context", "")
        prompt = _build_prompt(question, context, _history_pairs(req.history))

        streamed = ""
        try:
            for tok in rag_chat.ask_llm_stream(prompt):
                streamed += tok
                yield _sse({"type": "token", "t": tok})
        except Exception as e:  # noqa: BLE001
            if not streamed:
                yield _sse({"type": "error", "message": f"Ollama failed: {e} — is it running? `ollama run {config.OLLAMA_MODEL_NAME}`"})
                return

        validation = None
        if getattr(config, "GROUNDING_VALIDATION", False) and streamed.strip():
            cited = list(curated.get("main", [])) + list(curated.get("also", []))
            validation = rag_chat.validate_grounding(streamed, cited)

        payload = {
            "type": "final",
            "answer": streamed,
            "curated": {
                "main": [_clean_detail(d) for d in curated.get("main", [])],
                "also": [_clean_detail(d) for d in curated.get("also", [])],
            },
            "response_time": round(time.time() - t0, 1),
        }
        if validation is not None:
            payload["validation"] = validation
        yield _sse(payload)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/quiz")
def quiz(req: QuizRequest):
    """Verbatim quiz prompt from the original Streamlit UI — concept MCQs, no verbatim recall."""
    ctx_q = req.context.strip() or ""
    quiz_prompt = f"""You are HadeS, a teaching assistant. Create exactly 3 MCQs that test CONCEPTUAL understanding from the lecture context. Do NOT test verbatim recall of incidental examples.

Rules:
- Ground every question in the context — no outside facts.
- NEVER ask "What was the example value/name?" (e.g., What was dog/Alice/Sarah/age set to?). That is meaningless unless you memorized the transcript.
- If you reference an example, INCLUDE the full snippet in the question stem so it is self-contained. Good: 'Given `name = \\"Alice\\"` then `name = \\"Bob\\"`, what happens?' Bad: 'What was name set to?'
- Prefer WHY / HOW / APPLY: definitions, rules, why we use it, what breaks, how to fix.
- 4 options A-D, one correct. After each question add: **Answer: X — why (1 line, from context)**.
- Keep concise, exam-style. One question should involve code if context has it.
- Format as markdown:
### Q1: [self-contained question]
- A) ...
- B) ...
- C) ...
- D) ...
**Answer: B — ...**

Lecture context (sources for: "{req.question}"):
{ctx_q}

Now create the 3 concept MCQs:"""
    try:
        return {"quiz": rag_chat.ask_llm(quiz_prompt)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Ollama failed: {e} — is it running? `ollama run {config.OLLAMA_MODEL_NAME}`")


@app.post("/api/summary")
def summary(req: SummaryRequest):
    if not req.questions:
        raise HTTPException(status_code=400, detail="No completed questions to summarize")
    qs = "\n".join(f"- {q}" for q in req.questions)
    prompt = f"You are HadeS, an educational assistant. Summarize these student questions into 3 concise bullets. Be encouraging.\n\nQuestions:\n{qs}\n\nSummary:"
    try:
        return {"summary": rag_chat.ask_llm(prompt)}
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Ollama failed: {e} — is it running? `ollama run {config.OLLAMA_MODEL_NAME}`")


# ── static UI (plan Task 3.2) ─────────────────────────────────────────────────
# Served by this app, same origin as the API — which is what makes CORS and the Vite
# proxy dev-only concerns. In the frozen build the UI sits next to the exe (sys._MEIPASS);
# in dev it is just frontend/dist. HADES_REQUIRE_UI=1 turns a missing build into a hard
# error, used by the installer smoke test so it can never ship a UI-less package.

def _ui_dir() -> pathlib.Path:
    base = pathlib.Path(getattr(sys, "_MEIPASS", config.BASE_DIR))
    return base / "frontend" / "dist"


UI_DIR = _ui_dir()
if (UI_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(UI_DIR), html=True), name="ui")
elif os.environ.get("HADES_REQUIRE_UI") == "1":
    raise SystemExit(f"UI build missing at {UI_DIR} — run: cd frontend && npm run build")
else:
    print(f"[hades] no UI build at {UI_DIR} — API-only mode (dev: use Vite; packaged: build first)")


if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HADES_HOST", "127.0.0.1")
    port = int(os.environ.get("HADES_PORT", "8000"))
    if port == 0:
        # "pick a free port": probe for one, print it on a single line the desktop shell
        # can parse, then release it for uvicorn.
        # ponytail: tiny bind-probe race; hand uvicorn a pre-bound socket if it ever bites.
        import socket
        with socket.socket() as probe:
            probe.bind((host, 0))
            port = probe.getsockname()[1]
        print(f"HADES_PORT={port}", flush=True)
    print(f"HadeS API -> http://{host}:{port}  (model: {config.OLLAMA_MODEL_NAME}, profiles: {config.AVAILABLE_PROFILES})")
    # Preload in plain daemon threads alongside startup, never before it: these
    # must not occupy the request executor's workers.
    threading.Thread(target=_warmup, daemon=True, name="hades-warmup-index").start()
    threading.Thread(target=_warmup_llm, daemon=True, name="hades-warmup-llm").start()
    uvicorn.run(app, host=host, port=port, log_level="info")
