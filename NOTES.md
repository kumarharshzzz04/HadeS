# HadeS — state notes (2026-10-05, updated Oct 2026)

Fast recall of what changed, what measured, what failed. Update when state changes.

## Live (on by default)

- **Retrieval pipeline:** dense MiniLM `all-MiniLM-L6-v2` top-50 → cross-encoder rerank
  `cross-encoder/ms-marco-MiniLM-L-6-v2` (22.7M params, 88 MB, cold load 0.4 s) → top-6 →
  5-min cluster merge → A+B curation. `RERANK_ENABLED=True` in `config.py`.
  Cost: +0.8 s per question (retrieval+rerank ≈ 1.3 s).
- **Refusal:** `final` event with `declined=true` when best cosine < `MIN_RETRIEVAL_CONFIDENCE=0.35`.
  Measured: legit min 0.371 ("how to create venv"), off-topic max 0.251 ("capital of France").
- **Grounding validation:** `final` carries `validation {overall, claims[], passed}`.
  `GROUNDING_THRESHOLD=0.35`, `GROUNDING_PASS_RATIO=0.8`. MiniLM claim-vs-chunk: grounded 0.49–0.54,
  hallucinated 0.09–0.61. Works; no UI badge yet.
- **SSE contract:** `stage → token → final` (+ optional `declined`, `confidence`, `validation`). Frontend untouched.
- **Tests:** `python tests/test_retrieval.py` (BM25 rank, RRF, confidence, rerank ordering).
- **Env:** conda env `dl` is gone — run with anaconda base python
  (`/c/Users/kingh/anaconda3/python.exe`). Offline enforced via `HF_HUB_OFFLINE=1` in
  `rag_chat.py` / `server.py`; models cached under `~/.cache/huggingface/hub`.

## Verified end-to-end through the frontend (2026-10-05)

- `npm run build` (tsc -b + vite 8.3.2) exit 0. Ran backend :8000 + `npm run dev` :5173 together;
  `/api/health` + `/api/profiles` 200, zero console errors, zero server tracebacks.
- Profile switch reflects live server truth (HadeS Demo shows 611 chunks). Real question
  "how does pip install work?" streamed stages+tokens, finished in 45.7 s, cites ★ main lesson
  00:39:26–00:40:07 + 00:45:26–00:46:07 — i.e. the tuned retrieval is what the UI shows.
- Off-topic "capital of France" → decline message renders in the UI in 4.5 s, no sources, no crash.
- "Quiz me" → `/api/quiz` 200, 3 MCQs render with clickable A–D. `/api/summary` verified by curl
  (real 3-bullet summary). Study Guide looked like a dead button at 2/3 answered — **not a bug**: the
  export is a client-side blob download (`download()` in `Sidebar.tsx`), so it never shows up as a
  request. It is enabled from the first answered question (`disabled={!completed.length}`) and prints
  the ready count under it. Only the 3-question session summary is gated.
- Gap: the UI ignores `declined` / `validation` on the `final` event (no badge). The decline text
  appears only because the server sends that text as the answer.

## In-page player (Oct 2026)

- Source rows are now buttons: click expands a `youtube-nocookie` embed seeked to the cited second
  (`?start=<sec>&autoplay=1`), plus an external-link fallback. `parseYouTube()` lives in
  `frontend/src/lib/format.ts`; check: `node frontend/scripts/sources.check.ts`.
- `og` has no single video (`config.YOUTUBE_URLS` maps only hades_demo + quantum; runtime-verified:
  og → None) → rows render as plain non-interactive divs, no player, unchanged look.
- Fixed alongside: long labels used to overflow under the ★ Main lesson badge at narrow widths
  (time span was `shrink-0`) — name + time now truncate with `title` tooltips.
- Verified in mock mode (:5199, VITE_USE_MOCK=1): embed start=7605 and start=8955 render and play the
  right lesson, Watch→Hide toggle, external link hrefs correct, zero console errors; og row has
  0 buttons/links/iframes when seeded via localStorage. `npm run build` exit 0; oxlint 0 errors.

## Fast / Think answer mode — built, measured, reverted (Oct 2026)

- Tried a `mode` toggle on `/api/ask`: fast = heuristic curation (no curation LLM), short prompt,
  220-token cap (warm: 6.6 s / 186 chars) vs think = the old thorough pipeline (24.5 s / 1160 chars).
- Rejected in practice: fast's one-line answers were too short to be useful. Toggle, `AskMode`,
  the token cap and the prompt branch were removed; the single thorough pipeline is the one shipped.
  Do not resurrect without solving the length/quality gap first.
- One keeper from that work: launching via `uvicorn.run(server.app)` from a `python -c` import skips
  `if __name__ == "__main__"` and the warm-up thread, so the first request pays ~45 s of cold loads.
  `python server.py` and `dev.py` are unaffected.

## PRD (Oct 2026)

- `docs/PRD.md` (moved out of the repo root) — product requirements in my own voice: the problem, who it's for, the session flow, P0/P1/P2
  requirements with acceptance lines, non-functional budgets, success metrics, milestones, risks and the
  decisions log. Next revision when v2.1 lands.

## Product one-pager poster (Oct 2026)

- `onepager/index.html` — standalone tall poster (1440 × 1803), theme-matched to the app, self-contained:
  inline CSS, no build, no server, double-click to open. Google Fonts link with system fallbacks.
- Same leak rule as the in-app page: capability copy only — no stack names, no model names, no internals,
  no install steps. Charts use real repo numbers only (chunks 1,328 / 611 / 138; lengths 18h / 5h16m /
  1h36m; 11/11 retrieval eval; ~25 s warm grounded answer).
- Exports generated from the file, not hand-made: `onepager/hades-onepager.png` (2880 × 3620, 2×) and
  `onepager/hades-onepager.pdf` (single page; Chrome scales it to fit Letter).
- Regen: open the file in agent-browser, `set viewport 1440 1804 2`, `screenshot --full`, `pdf`.
- Verified: poster fits one 1440-wide screenshot with no scroll, chart labels no longer truncate,
  11/11 dots legible, PNG + PDF regenerated after the last edit, PDF = 1 page. Caveat: the print
  page has a little dark slack below the content (Chrome pagination rounding).

## "What is HadeS?" explainer page (Oct 2026)

- New in-app page (`view: "about"` in App.tsx; opened from the landing hero and the chat sidebar;
  Back returns wherever it was opened from). `frontend/src/components/hades/About.tsx`.
- Copy is deliberately capability-only: no stack names, no pipeline internals, no library logos —
  a bento of six animated cards in the chrome theme, all `framer-motion`, reduced-motion aware.
- Verified in mock mode (:5196): typing loop cycles (152-char answer → hold → restart), grid is
  3-col at 1440 / 2-col at 910 / 1-col at 390, no horizontal overflow, both entry points and
  back-to-origin work, zero console errors; `npm run build` exit 0, oxlint 0 errors, quiz + sources
  checks pass. The reduced-motion branch was code-reviewed only at the time; **re-verified Oct 2026**
  with `agent-browser set media dark reduced-motion` — the typed answer mounts complete (152 chars, no
  caret) and the six cards render with no entrance animation. Not a limitation any more.

## Quiz re-generation fix (Oct 2026)

- Bug: "Regenerate quiz" (RotateCcw) replaced `chat.quiz` but `QuizBlock`'s `picked` state
  survived, so the new quiz rendered pre-answered — old selections locked the options and
  printed verdicts against the previous picks. Root cause of "player works, requiz doesn't".
- Fix: `ChatMessage.tsx` bumps a `quizEpoch` on every successful generation and keys
  `QuizBlock` with it → remount clears picks even when the server returns identical text.
  Rotate button is disabled + spins while the request is in flight (was double-firable,
  zero feedback).
- Side fix in `quiz.ts`: `RE_ANSWER` now eats the separator dash after a closing `**`
  (`**Answer: B** — why`), which used to leave `— why` in `why` → UI printed "— — why".
- `mock-api.ts` `mockQuiz` alternates two sets; replaying one identical script made
  regeneration look like a no-op in demo mode.
- Verified mock mode :5199: answer Q1 → Regenerate → `Answered 0/3`, options enabled, next
  click swaps question set; verdict line single-dash; zero console errors.
- Verified real backend too (:5188 proxied to :8000, llama3:8b): Q1 answered → Regenerate →
  `/api/quiz` 200 returned a completely different 3-question set, `Answered 0/3`, no stale
  verdict, zero console errors. `quiz.check.ts` / `sources.check.ts` pass, oxlint 0 errors,
  `npm run build` exit 0.

## Landing bento (Oct 2026)

- `frontend/src/components/hades/LandingBento.tsx` — new section between the globe hero and the cinematic
  footer: six near-equal cards (ask in plain words / citation / player / quiz / course diagram / privacy)
  in the UIAble card grammar, capability-only copy, shadcn tokens, all illustrations inline.
- `Landing.tsx`: the chevron cue now scrolls to the footer wrapper ref instead of `window.innerHeight` —
  the bento broke the old one-viewport assumption (verified: cue click → scrollY 1768 vs wrapper
  offsetTop 1769, reveal starts at the viewport top).
- `CinematicFooter.tsx`: the "Ollama llama3 · FAISS · Whisper" pill was the last place a public page named
  the stack (PRD §11 rule) → "Transcribes, searches and answers locally".
- Verified: build + oxlint clean; 3 columns @1440, 2 @910, 1 @390 (326 px cards), no horizontal overflow,
  zero clipped text in the section, all six cards reach opacity 1 on scroll, console empty.
- Reduced motion verified for real this time, not code-reviewed: `agent-browser set media dark
  reduced-motion` → cards mount at `opacity: 1`, `transform: none` while still 844 px below the fold, so
  the animation is genuinely skipped rather than deferred to first scroll.
- Artifact: `.freebuff/verify/landing-390.png` (780 × 1688 @2×, gitignored). Note for future sessions: the
  built-in preview screenshotter only composites at a 1440-wide viewport here — use agent-browser for
  other sizes.

## Doc audit (Oct 2026)

- Read PRD / README / NOTES / EVAL against the code. PRD moved to `docs/PRD.md` and the README tree
  now points at it. Two claims were stale and are corrected: the
  study-guide "silent button" risk in PRD §10 (see above — client-side download, not a request) and this
  file's own note about it.
- Removed dead `splitLabel()` from `frontend/src/lib/format.ts` — `SourceList.tsx` has its own local
  `splitSafe()` and nothing imported the format.ts copy.
- Numbers that still disagree across docs, left for a human call rather than quietly edited:
  NOTES' automated span sweep says **10/11** (one ground-truth quirk) while EVAL.md and the PRD say
  **11/11**; and PRD §6 calls ~25 s the warm answer while the verified end-to-end run through the UI
  measured 45.7 s (NOTES lists the spread as 15–48 s).
- Known gaps still open: follow-ups ignore chat history at retrieval, hybrid BM25 stays parked, no
  confidence/validation surface in the UI (by decision), 1.8 MB single JS chunk (no code splitting).

## Failed experiments (do not redo blind)

- **Hybrid BM25+RRF (plan 1.2):** built, stdlib only, `RETRIEVE_MODE="dense"` default.
  Measured 7/11 vs dense 9/11 — BM25 ranks recap sections over teaching moments and RRF
  displaces the dense top-1. Code stays for when a reranker can filter the fused pool.
- **Embedding swap `bge-small-en-v1.5` (plan 1.1):** 129 MB, 384-dim, with rerank: 6/11 vs
  MiniLM 8/11. Margins flat (junk 0.797 vs lesson 0.775), grounding collapsed (hallucinated
  passed 1.00). Rolled back, indexes restored, reason recorded in `config.py`.
- **Big reranker `BAAI/bge-reranker-v2-m3` (plan 1.3):** 2.3 GB, skipped as too heavy.
- **LLM swap (plan 2.1):** `qwen3:8b` not local (+4.7 GB). `qwen2.5-coder:7b` A/B: 28 s vs
  llama3:8b 14 s; grounding 0.74 fail vs 0.86 pass. Keep `llama3:8b`.
- **Chunk-size sweep (hades_demo, production config, `use_llm=False`):**
  - 700/100 (current, 611 chunks): **8/11** (real miss: `strings` only; `git`/`programming` are
    EVAL ground-truth quirks — retrieval correct there).
  - 500/80 (918 chunks): 7/11 — broke `venv` (05:02 junk), fixed nothing.
  - 1000/200 (445 chunks): 4/11 — broke `pip`, `data types`, `numbers`, `venv`.
  - Decision: keep **700/100**. `strings` miss is NOT a chunk-size problem: dense top-1 is
    the right chapter (01:13:29) while heuristic curation picks the f-string cluster (01:31)
    via its define/syntax bonuses → suspect the curator, not the chunks.

## Curator fix (live, Oct 2026)

- `_ordered_main_clusters()` in `rag_chat.py`: a **confident dense top-1** (cosine ≥
  `MAIN_PRIOR_MIN_COSINE=0.5`) leads the ★ mains; a weak one defers to `_teaching_score`.
  Remaining picks sort by teaching score → deterministic order (no more LLM order flake).
  If the curator drops a confident top-1, it swaps out the last pick.
- Measured: fallback sweep 8/11 → **10/11**; `strings` fixed (01:13:29 first),
  `functions` preserved (weak top-1 0.484 → heuristic keeps 02:06:45), `pip`/`git` pass.
  LLM path: `data types` now lists the correct chapter first.
- Known limit: when the top-1 is weak, the LLM's *set* can still omit the right cluster for
  that run (e.g. `functions` picks 03:48 sometimes); ordering is stable, set choice varies.

## EVAL status (hades_demo, production config, `use_llm=False` sweep)

- Automated span score **10/11**. Only remaining MISS is `programming` — EVAL ground-truth
  quirk; retrieval returns the actual 00:51 chapter.
- Answer latency ~15–48 s (llama3 on laptop).
- Open bugs: LLM curator set-choice variance on weak priors (above); follow-ups ignore
  chat history at retrieval; no inline timestamp citations in answers; EVAL spans messy.

## Research anchors

- Anthropic contextual retrieval: −35 % failures contextual embeddings, −49 % with contextual
  BM25, −67 % with rerank. Their tests showed generic summaries and HyDE add little.
- hades_demo chunks: 700 chars / 100 overlap (hardcoded override in `chunk_transcripts.py`),
  611 chunks, exact Whisper timestamps.

## Launcher + streaming fixes (Oct 2026)

Reported symptoms: `HadeS.bat` took 1–2 minutes, sprayed cmd windows that closed again,
and the app claimed it "couldn't reach the HadeS server"; answers arrived in lurches
("raggedy") instead of streaming.

What was actually happening (measured, not guessed):

- **The backend was running.** The screenshot's error is an *Ollama* refusal on :11434
  (`WinError 10061`) relayed over SSE, but the UI rendered it with the generic
  "Couldn't reach the HadeS server — start it with `python server.py`" copy, which made a
  healthy backend look dead. `api.ts` now throws a distinct `ServerError`; `App.tsx`
  gives the Ollama case its own message.
- **Startup slowness was port probing, not Python.** A serial sweep of 5173–5179 cost
  ~0.7 s per closed port (urllib on Windows adds proxy/DNS fallback: 4.7 s per sweep, run
  twice) and `_backend_up()` burned ~5 s on a closed port. Sweeps are now parallel and
  socket-gated. Measured boot to Ready: 31.3 s → **13.4 s** (backend up at +5.9 s).
  Every `[dev]` line now carries an `(+Ns)` timestamp so the slow step is visible.
- **Two code paths could kill the machine's other processes.** `_force_tree_kill` ran
  `taskkill /F /IM node.exe` (every Node process, not just this project), and `_kill_tree`
  ended with an unconditional port-owner kill, so exiting one launcher killed a *reused*
  backend or another app's server on :8000/:5173. `_is_hades_child` also never matched
  (it looked for "server.py" in `tasklist` output, which only prints image names). Kills
  are now scoped to processes whose command line proves they belong to this project, and
  every helper/child is spawned with `CREATE_NO_WINDOW` so nothing can flash.
- **Re-launching started duplicate stacks** — a second backend attempt plus a second Vite
  on the next port, each run then fighting the other. Launching `dev.py` while HadeS is up
  now detects backend + a frontend answering with "HadeS" in the HTML and just reopens the
  browser (verified: second launch reused PIDs 8500/12964, started nothing).

Streaming (the real fix):

- Ollama's default 5-minute unload meant every pause cost a fresh model load — measured
  first token at **25–33 s** after the question. `rag_chat.warmup_llm()` now loads the model
  during server boot and both Ollama calls send `keep_alive` (`OLLAMA_KEEP_ALIVE="6h"`).
- Token delivery was never the problem: the SSE path delivers one token per ~120 ms with
  zero sub-20 ms clumps (backend probe and in-page probe through the Vite proxy alike).
  The DOM was the problem: React re-parsed markdown + rehype-highlight for every token,
  which starved the render thread so the answer landed as **one commit with all 1465 chars**.
  `AnswerMarkdown` now renders plain text while streaming (caret kept via
  `.hades-stream-plain`) and parses markdown once at the end; `App.tsx` buffers tokens and
  flushes on a 60 ms timer. Same measurement after: **185 incremental commits**, median
  jump 4 chars, max 11 — text grows continuously instead of in blobs.

Caveat kept honest: console-window counts during a boot could not be measured from the
agent shell (`tasklist` needs `MSYS_NO_PATHCONV=1` there), so the window-flash claim rests
on the code paths above rather than a count. The 12 s Ollama wait when Ollama is down is
now 30 s with progress lines, because a cold `ollama serve` was passing the old 12 s window
and then failing every answer.

Probes used are throwaway: `.freebuff/watch.sh`, `.freebuff/stream-probe.py` (gitignored).

## Speed regression: Ollama ran on CPU, and the refusal gate flipped (Oct 2026)

Reported: answers at 112 s where they used to be ~10 s, plus "I couldn't find this in the
lectures" on legitimate questions. Neither was temperature, prompt wording, nor any UI
feature (git: `LLM_TEMPERATURE`/`LLM_MAX_TOKENS` and the ask prompt have never been edited;
player/quiz/copy are UI-only).

- **Root cause of the slowness: the running Ollama server was CPU-only.** `/api/ps` showed
  `size_vram: 0` and generation at 9.2 tok/s with the RTX 4050 at 0 % and 16 MiB used. Its
  own log had discovered CUDA at 10:09, so the GPU was lost later (sleep/resume or a driver
  hiccup kills the CUDA context; the server never re-discovers).
- **Fix: restart `ollama serve`.** A fresh server logs `library=CUDA compute=8.9 cuda_v13`,
  offloads **27/33 layers**, and benchmarks **22.8 tok/s** with 3994 MiB resident. Killed the
  stale pid, the tray app respawned it. This is environment, not code: no repo change fixes it.
- Math on the number they saw: `LLM_MAX_TOKENS=900` at 9.2 tok/s ≈ 98 s + retrieval ≈ 112 s.
  Same cap on GPU ≈ 45 s worst case. Measured after: `hades_demo` "What is a variable?" —
  first token ~3.5 s, 202 tokens, **13.4 s total**, gap median 47 ms (was 121 ms CPU).
  `og` answers take ~38 s because retrieval/rerank/curation run over 1328 chunks.
- **Refusal gate fixed (rag_chat.curated_confidence).** It read confidence from the clusters
  the curator *picked*, so the same question flipped: `og` "What are functions?" (a starter
  chip in the UI) scored 0.234 → DECLINED, while the app had answered it earlier. It now takes
  the best score from the retrieved pool. Re-measured: og legit 0.395–0.409 (answers),
  og off-topic 0.144/0.228 (still declined), hades_demo off-topic 0.331 (declined).
  Regression test added: `tests/test_retrieval.py::test_confidence_includes_retrieved_pool`.
- **Streaming look reverted to markdown.** Plain-text-while-streaming was the CPU-starvation
  workaround; with the model on the GPU it is no longer needed and raw `**`/`###` mid-stream
  looks broken. Measured with markdown flowing: **206 commits, median jump 7 chars, max 20**
  (the CPU-only era was one commit of all 1465 chars). Keep the 60 ms token batching in
  `App.tsx` — that is what keeps the re-parse affordable.
- **Still open:** if Ollama goes CPU-only again after a sleep, every answer doubles in time.
  Recovery: quit Ollama from the tray, rerun `HadeS.bat` (dev.py starts a fresh server). A
  boot-time guard (detect `size_vram == 0` after warmup, restart once) is not implemented.

## Codebase review pass (Oct 2026) — findings only, nothing changed

The working state is saved as **commit `6bd0762`** ("smooth streaming, tighter refusals,
and demo-ready polish") — local only, nothing pushed. This section is a to-do list, not a
changelog: no code was touched. Order = what I'd fix first.

### Verified this pass (so the green below is real, not assumed)

- `python tests/test_retrieval.py` → all passed. `frontend/scripts/{quiz,sources,stream-text}.check.ts`
  → exit 0 each. `npm run build` → exit 0. `npx oxlint` → 0 errors, 4 warnings (all benign, see B6).
- Live backend (all through `http://127.0.0.1:8000/api`, model warm on GPU):
  `/health` 200 in 2.0 s (`ollama: true`), `/profiles` 200, `/ask` streamed 263 tokens,
  first token 4.1 s, total 25.6 s; `/quiz` 11.3 s; `/summary` 16.4 s. `/api/ps` → `llama3:8b`
  `size_vram=4.19GB` (fully offloaded, expiry 23:23) — GPU path healthy right now.
- Throughput note: 263 tokens / 21.5 s ≈ **12 tok/s** in that run, not the 22.8 tok/s measured
  before. Nothing is broken (VRAM is full), but re-run the timing the morning of the demo —
  and re-check `/api/ps`. If it drops to `size_vram=0` it's the CPU-fallback problem below.

### A. Fix before stage (small edits, low risk)

1. **Stale launcher name in the error copy.** `frontend/src/App.tsx:167` tells the user to run
   `HadeS.bat` — that file does not exist in the repo (grep: only App.tsx and this file mention it).
   One-line copy fix → `` python server.py `` or `` python dev.py ``.
2. **A mid-answer stream death throws the partial answer away.** `server.py` deliberately swallows
   the Ollama error when *some* tokens already streamed (`if not streamed:`), so no `final` event is
   ever sent. `api.ts` then throws "The server closed the stream before finishing the answer.",
   and `App.tsx`'s catch **replaces the whole answer** with the "Couldn't reach the server" block.
   So a 90 %-complete paragraph dies with the model. Cheapest fix: have the server emit `final`
   with the partial text (`truncated: true`) instead of staying silent; the UI then keeps the text
   and can show a one-line "this answer was cut short". ~10 lines, no behaviour change on the happy
   path. Not reproduced live (needs Ollama to die mid-answer).
3. **No guard for Ollama silently dropping to CPU.** Already in this file as the #1 open risk: after
   sleep/driver hiccup the model runs at 9.2 tok/s and every answer doubles (⩽45 s → ⩽112 s). A
   boot-time check is cheap: after `warmup_llm()`, GET `/api/ps`, and if `size_vram == 0` log a loud
   warning (or restart `ollama serve` once). Doing nothing keeps a stage risk that no UI change fixes.

### B. Dead code / drift — safe deletions, do them when bored

4. **`ChatMessage.sources` is never read.** Grep for `.sources` across `frontend/src` → zero hits.
   `curated` replaced it. Drop the field from `types.ts`, the `sources: []` initializer in `App.tsx`,
   and the matching mock shape. 3 lines.
5. **`frontend/src/components/hades/OrbStatus.tsx` is unused.** Zero references outside itself.
   Delete the file (this also removes one of the 4 lint warnings).
6. **`_history_pairs()` in `server.py` is a passthrough** with a comment arguing with itself.
   Inline it at the one call site.
7. **Two unused compat wrappers in `rag_chat.py`:** `search_chunks_simple()` and
   `search_chunks_detailed()` have no callers (the server only uses `search_chunks_curated`).
   Delete both, and `search_chunks()` with them if the tests don't need it.
8. **Grounding validation is computed and thrown away.** `validation` rides the `final` event;
   nothing in `frontend/src` mentions it. Measured cost is only **0.15 s** (7 claims, MiniLM batch)
   — I expected seconds and was wrong, so this is dead weight, not a latency bug. Either surface a
   "3/7 claims supported" badge (it currently reports `passed=False`, `overall=0.43` on a legit
   answer, so a naive badge would look alarming) or set `GROUNDING_VALIDATION=False`.
9. **Hybrid BM25 + RRF stays parked** (`RETRIEVE_MODE="dense"`, measured 7/11 vs dense 9/11). ~90
   lines nobody runs. Keep only if the reranker-filter plan is still alive; otherwise it's the
   biggest deletion available.
10. **The frontend checks are wired to nothing.** `scripts/*.check.ts` need
    `node --experimental-strip-types <file>` and there is no npm script that runs them, so they rot
    silently. One line in `package.json`: `"check": "node --experimental-strip-types scripts/quiz.check.ts && ... && ..."`.
11. **4 oxlint warnings, all fine to leave:** 3 × `only-export-components` (`ui/badge.tsx`,
    `ui/button.tsx`, and 5's `OrbStatus.tsx`) and 1 × `set-state-in-effect` in `Sidebar.tsx` — that
    last one is intentional (re-read misses when the dataset changes).

### C. Structural (only matters if two tabs / two datasets at once)

12. **`rag_chat` keeps the active profile in globals** (`_active_profile`, `_index`, `_metadata`,
    `_bm25`) and `set_profile()` nulls them on switch. `/api/ask` sets the profile per request. So a
    second tab (or a quiz request in another dataset) can swap the globals **mid-retrieval**, and the
    first request then reads the other profile's metadata → citations/labels/timestamps from the
    wrong dataset. Single tab = never happens; it's on stage = single tab too. Real fix means
    threading `profile` through the call chain instead of globals (~a refactor, not a patch).
    Recommend: leave it, and never switch datasets while an answer is streaming.

### D. Retrieval facts worth knowing before you tune anything

13. **On `hades_demo` the LLM curation pick never runs.** Measured with the live index: 12 candidates
    collapse to **2 clusters** (the whole profile is one file, every chunk inside the 300 s window),
    and `_llm_pick_main` returns early whenever `len(clusters) <= main_k`. So demo answers come from
    clustering + `_teaching_score` + `MAIN_PRIOR_MIN_COSINE`, and the curation prompt costs 0 s
    because it is skipped. Tune `_teaching_score`, not the curator prompt, and don't "optimize" the
    curation call on this dataset.
14. **Refusal margins are thin on purpose.** hades_demo off-topic 0.331 vs gate `0.35`, legit floor
    0.371 — 0.04 of headroom on both sides. Any threshold change trades a decline for a leak. Best
    mitigation is procedural: run your three stage questions once, right before you present.
15. **`_teaching_score` hardcodes corpus-specific strings** (`"dog"`, `"csv"`, `"def "`) — a
    deliberate hack for this lecture, not a general heuristic. Fine; just don't extend it and assume
    it will generalize to `quantum`.
16. **`_local_snapshot()` hardcodes `C:/Users/kingh/.cache/huggingface/hub`** as an extra search
    path (the home-dir entry covers other machines). If you demo on a laptop, run one warm question
    first: a missing local snapshot sends `get_model()` to the network path and, offline, that is the
    old 2-minute HF retry hang.
17. **Numbers still disagree across docs** (10/11 vs 11/11, ~25 s vs 45.7 s warm) — flagged in the
    doc-audit section above and left alone again. Pick one number per claim when the PRD is next
    revised.

### E. Not covered by this pass

- Stop button, `VITE_USE_MOCK=1` demo mode, dataset switching mid-session, Study-guide download,
  in-page player, and the refusal path through the UI were **not** re-exercised (earlier runs in this
  file cover them for the code as it was then; this pass changed nothing, so those results still hold).
- Nothing here was reproduced by breaking something on purpose — items 1–3 are read from the code
  paths plus the timings above.

## Commands

- Retrieval check: `python tests/test_retrieval.py`
- Re-chunk: `python chunk_transcripts.py --profile hades_demo` (delete old `*_chunk_*.txt` first)
- Re-embed: `python create_embeddings.py --profile hades_demo`
- Serve: `python server.py` or `python dev.py`; health: `curl localhost:8000/api/health`
- Profiles: `og` (top-level index), `hades_demo`, `quantum` under `profiles/`.
