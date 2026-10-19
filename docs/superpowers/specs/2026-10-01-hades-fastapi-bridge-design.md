# HadeS — FastAPI Bridge Design

Date: 2026-10-01
Status: Approved (design agreed in session; user approved build)

## Goal

Connect the React frontend (`frontend/`) to the existing, working Python RAG
backend (`rag_chat.py`) so real retrieval replaces mock data. **Zero changes
to `rag_chat.py`, `config.py`, or any pipeline script.**

## Non-goals

- No rewrite of retrieval, curation, chunking, or prompting logic.
- No multi-user features, auth, or persistence beyond what exists.
- Streamlit (`ui.py`) keeps working unchanged, side by side.

## Architecture

One new file `server.py` at the repo root: FastAPI app that imports
`rag_chat` and exposes its existing functions over HTTP/SSE.

```
React (5173) --/api proxy--> FastAPI server.py (8000) --imports--> rag_chat.py
                                                                   ├─ FAISS + metadata (profiles)
                                                                   ├─ sentence-transformers (offline)
                                                                   └─ Ollama llama3:8b (localhost:11434)
```

- Vite already proxies `/api` → `localhost:8000` (configured in vite.config.ts).
- CORS: allow the Vite dev origins.

## Endpoints

| Endpoint | Method | Wraps | Behavior |
|---|---|---|---|
| `/api/health` | GET | ollama ping | `{ok, ollama}` — used for status surfacing |
| `/api/profiles` | GET | `rag_chat.list_profiles()` | `[{name, ready, chunks}]` |
| `/api/profiles/{name}` | POST | `rag_chat.set_profile()` | switch active dataset server-side |
| `/api/ask` | POST (SSE) | `search_chunks_curated()` → history-aware prompt → `ask_llm_stream()` | events: `stage(searching)` → `stage(solving)` (once the call is past the sub-second FAISS phase and the curation LLM is the long pole) → `stage(composing)` → `token`* → `final{curated, response_time}` |
| `/api/quiz` | POST | `ask_llm()` | the exact concept-MCQ prompt from ui.py, grounded in the message's retrieved source texts |
| `/api/summary` | POST | `ask_llm()` | the exact 3-bullet summary prompt from ui.py |

SSE payload format: `data: <json>\n\n`, one event object per line group:
`{"type":"stage","stage":"searching"}`, `{"type":"token","t":"…"}`,
`{"type":"final","curated":{…},"response_time":1.2}`.

`curated` payloads are the frontend's existing `SourceDetail`/`CuratedResult`
shapes (raw `cluster` lists stripped before serialization).

## Prompt parity

Ask/quiz/summary prompts are copied verbatim from `ui.py` (including
`CHAT_HISTORY_TURNS=3` history injection formatted `User: …/Assistant: …`),
so answers match OG HadeS exactly.

## Frontend changes (thin)

- New `frontend/src/lib/api.ts`: same callback contract as `mock-api.ts`
  (`onStage/onToken` → resolve `{answer, curated, response_time}`) implemented
  with `fetch` + ReadableStream SSE parsing.
- `App.tsx`: `mockAsk` → `ask` from api.ts; profiles fetched from `/api/profiles`
  and merged over the static display metadata (falls back to static if server
  is down).
- `ChatMessage.tsx`: quiz calls `/api/quiz` with the message's source texts.
- `Sidebar.tsx`: summary calls `/api/summary`.
- `mock-api.ts` stays; selected via `VITE_USE_MOCK=1` for Ollama-less demos.
  If the server is unreachable in real mode, the chat shows an honest error
  message instead of silently faking answers.

## Environment / running

- Deps added to requirements.txt: `fastapi`, `uvicorn`.
- Run: `python server.py` (uvicorn on 8000, reload off) + `npm run dev`.
- Ollama must be running with `llama3:8b` pulled (existing setup).
- Offline env vars (`HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE`,
  `KMP_DUPLICATE_LIB_OK`) set in server.py before importing rag_chat, same as
  rag_chat does itself.

## Error handling

- Unknown profile → 404.
- Missing index for profile → 500 with the build command in the detail.
- Ollama down → `/api/ask` SSE emits a final `error` event; UI shows HadeS's
  honest failure message ("is Ollama running? `ollama run llama3:8b`").
- Frontend fetch failure (server not started) → chat message with the exact
  remedy.

## Testing

1. `curl /api/health`, `/api/profiles` against the built `hades_demo` index.
2. SSE smoke: POST `/api/ask` "what are functions" → stage/token/final events.
3. UI end-to-end: ask → sources with real labels → quiz → summary → export.
4. EVAL.md's 11 questions as a retrieval regression smoke test.

## Out of scope (later)

- BM25/rerank upgrades (README future items), voice input, auth.
