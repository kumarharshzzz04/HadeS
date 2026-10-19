# Batch 5 — In-app ingest: paste a link, get a course

> **For agentic workers:** this is a *design/spec*, not an executed batch. Nothing here is
> implemented. Like the rest of `app plan/`, it is executed task by task and a task is done only
> when its **Done when** gate passes. This batch is `independent` of Batches 0–4.
>
> **Before starting task 5.1, the Open Questions at the bottom must be answered.** They change
> tasks 5.4, 5.6 and 5.7.

**Goal:** inside the installed app, the user pastes a lecture link, watches real progress, reviews
the transcript it produced, and then asks questions against that lecture with exact timestamps —
a new course in the sidebar, alongside `og`, `hades_demo` and `quantum`.

**Why:** today HadeS can only answer from three courses frozen into the build. The whole ingest
chain exists in this repo — but as CLI scripts that need a dev environment
(`download_hades_demo.py` → `transcribe_parts.py` → `chunk_transcripts.py` →
`create_embeddings.py`), and all of it is deliberately excluded from the shipped app. That is
fine for the original courses and useless for a user who wants their own lecture in there.

**Non-goal:** replacing the retrieval stack. Batch 5 adds a producer of courses; `rag_chat.py`
behaviour must not change.

---

## 1. What exists today, and what actually blocks this

Evidence, not memory. All line numbers from the current tree.

| Piece | State | Blocks what |
|---|---|---|
| `config.AVAILABLE_PROFILES = ["og", "hades_demo", "quantum"]` (`config.py:20`) | hardcoded list | every new course, everywhere |
| `rag_chat.set_profile()` (`rag_chat.py:24`) | raises `ValueError` for any name not in that list | switching to a user course |
| `transcribe_parts.py:30`, `chunk_transcripts.py:5`, `create_embeddings.py:12` | each takes `--profile` with `choices=config.AVAILABLE_PROFILES` | running the pipeline for a new course |
| `config.profile_paths()` (`config.py:35`) | resolves under `BASE_DIR/profiles/<name>` — inside the **install dir** | where a user course can live |
| `packaging/exclude.txt` | excludes the four ingest scripts and `video/ audios/ transcripts/ chunks/` | the pipeline simply is not in the app |
| `packaging/backend.spec` `excludes` | `yt_dlp`, `faster_whisper`, `ctranslate2`, `av` | downloading and transcribing |

The install dir is writable per-user (`%LOCALAPPDATA%\Programs\HadeS`), but user data must not
live there: it is the uninstaller's territory, and the docs already promise settings survive an
uninstall. So courses belong in the state dir, which already exists
(`config.state_dir()` → `%LOCALAPPDATA%\HadeS`, plan §7 / decisions §7).

**Measured facts that shape the design** (this machine, this session):

- `yt_dlp` is **pure Python** — 0 compiled extensions, 20.4 MB, v2026.08.19. YouTube breaks
  extractors regularly; a pure-Python package can be updated *without rebuilding the app* by
  dropping a newer wheel into the state dir and prepending it to `sys.path`.
- A 19-minute lecture (3Blue1Brown, `aircAruvnKk`) has **creator-provided English subs**: 286
  cues, mean 3.5 s, median 3.6 s, covering **90 %** of the timeline, 3,357 words, **no rolling
  duplicates**. Subtitle-only fetch is ~27 KB and takes seconds.
- Requesting `--sub-langs "en.*"` asks for ~33 translated tracks and YouTube answered
  **HTTP 429 Too Many Requests**. Language selection must be pinned, not wildcarded.
- Auto-captions were also listed for that video (12 languages before I stopped reading the
  output), so "no captions at all" is the exception rather than the rule — but see §2, because
  auto-captions are not the same thing as captions, and that video *also* had creator subs.

---

## 2. The transcript-quality problem (front and centre)

The user's objection is correct and it is the highest-risk part of this batch: **auto-generated
captions are unchecked machine output.** They are the *entire* ground truth the RAG indexes; if a
term is wrong, it is wrong in a way that hurts twice — the embedding drifts, and BM25 can never
match the token the user typed.

This is not hypothetical. Our own `quantum` course was transcribed locally with Whisper and the
transcript contains **"Shaw's algorithm"** and **"Schur's algorithm"** where the lecturer says
*Shor's*. That is why searching the corpus for the algorithm's real name is awkward, and it is
the same failure class that auto-captions produce (different engine, same mistake). A caption
pipeline that ignores this would quietly make the app worse than the courses we shipped.

**Design response — four independent defences, in order:**

1. **Source ladder, never "just captions".** Prefer the creator's own subtitle track
   (`--write-subs`); only fall back to `automatic_captions` (`--write-auto-subs`); only if
   neither exists does the Whisper path matter (Open Question 1). `yt_dlp` reports which tracks
   are which in the video's info JSON — the app records the source it used (`manual_subs` |
   `auto_subs` | `whisper`) in `source.json`, and **says so in the UI**. A user must know whether
   they are trusting a human transcript or a machine one.
2. **Quality gate before indexing.** Compute and store, per transcript: cue count, mean cue
   duration, timeline coverage %, whether cues roll (duplicate windows), and the share of cues
   with no terminal punctuation. A track that covers < 60 % of the runtime or rolls heavily is
   flagged **low quality** and the app offers the Whisper path instead.
3. **Term repair, reviewable and reversible.** Build a glossary from the video title,
   channel, and description, plus words the user adds. Flag any transcript token that is
   *near* a glossary term but not equal (Levenshtein-normalised, `Shaw's → Shor's`,
   `Kunth → Knuth`). Show the flagged segments, offer one-click "replace all occurrences",
   and keep the original text so the fix can be undone. Deliberately **not** an LLM rewrite of
   the transcript: a rewrite can invent sentences, and a hallucinated sentence in the index is
   worse than an ASR error.
4. **Human review before the course goes live.** The ingest completes in state *ready for
   review*; the course is searchable only after the user presses **Index this course** on the
   review screen. The review screen shows the title/channel/duration/subtitle source, the
   quality numbers, and the first ~10 flagged segments. Skipping review is one click, and the
   skip is recorded in `source.json` (`reviewed: false`).

Whisper's own output gets the same treatment: `faster-whisper` returns per-segment
`avg_logprob`/`no_speech_prob`, so low-confidence segments can be flagged before review rather
than after the user has been burned by a bad answer.

---

## 3. Architecture

One implementation of the pipeline, two entry points. The scripts become thin wrappers so the
dev flow (`python transcribe_parts.py --profile X`) keeps working and the app imports the same
code — no duplicated logic, no drift.

```
ingest/
  __init__.py
  registry.py    # course list/resolve/create: bundled courses + state-dir courses
  fetch.py       # URL → metadata + subtitle tracks (yt_dlp, subtitle-only)
  subs.py        # VTT/SRT → normalised segments; rolling-cue detection and dedupe
  audio.py       # URL/file → decoded audio (PyAV, no ffmpeg.exe) — Whisper path only
  transcribe.py  # faster-whisper → segments with confidence  — Whisper path only
  quality.py     # the §2 signals + glossary term flags
  chunk.py       # moved from chunk_transcripts.py, profile-agnostic
  embed.py       # moved from create_embeddings.py, profile-agnostic
  jobs.py        # job model, single worker thread, progress events, cancellation
```

`rag_chat.py` and `config.py` stop owning the course list: `registry.list_courses()` returns
bundled (`BASE_DIR/profiles/*` + `og`) **and** user courses (`state_dir/courses/*`), and
`set_profile()` takes a resolved course object. `config.AVAILABLE_PROFILES` stays as a derived
convenience for the old CLI scripts so nothing else breaks.

**Storage** (`%LOCALAPPDATA%\HadeS\courses\<slug>\`):

| File | Contents |
|---|---|
| `source.json` | url, id, title, channel, duration, subtitle source, yt-dlp version, `reviewed`, timestamps |
| `subtitles/<lang>.vtt` | raw track as fetched — kept so a re-process needs no re-download |
| `transcript.json` | segments `{start, end, text, confidence?}` + quality summary |
| `glossary.json` | candidate terms and the user's accepted replacements (audit trail) |
| `faiss_index.bin`, `metadata.pkl` | the artefacts `rag_chat` already knows how to load |

**Job model.** One worker thread, one job at a time (an ingest is CPU-heavy; two in parallel
would thrash a laptop). Jobs live in `state_dir/jobs/<id>.json` with a `stage` (`fetch →
transcribe → quality → chunk → embed → review`) and a monotonic progress value, so the UI can
show real progress and a crash can be resumed or discarded. Stages emit SSE events on the
`/api/ingest/<id>/events` endpoint, matching how `/api/ask` already streams. Cancellation sets a
flag the worker checks between batches; a cancelled job deletes its partial directory.

**Writes are atomic**: everything is built under `courses/.tmp-<id>/` and renamed into place when
the course is indexed, so a half-built course can never appear in the sidebar.

---

## 4. Size and dependency budget

Measured baseline: bundle 954 MB, installer 376,034,996 bytes (359 MiB).

| Addition | Cost | Needed by |
|---|---|---|
| `yt_dlp` (pure Python, no extensions) | **+20 MB measured** | every link ingest |
| `PyAV` decoding | ~30 MB (currently excluded as `av`) | Whisper path only |
| `faster-whisper` + `ctranslate2` | ~150–250 MB with DLLs (currently excluded) | Whisper path only |
| Whisper model `base` / `small` (downloaded on first use, not bundled) | 142 MB / 466 MB in state dir | Whisper path only |
| `ffmpeg.exe` | **not needed** — PyAV decodes in-process, avoiding a 70–100 MB binary | — |

So: the caption-first design costs **~20 MB** over today; the Whisper fallback adds ~180–250 MB
of bundle plus a model in the user's state dir. That difference is Open Question 2.

Sizes are a product decision: the plan's global constraint is a 1.5 GB install budget, we are at
954 MB today, and both options fit inside it.

---

## 5. UI surfaces

1. **Add a lecture** — a new sidebar entry opening a page with one URL field, a **Fetch** button,
   and the detected title/channel/duration/subtitle source shown before anything is transcribed.
   Cancel at any point.
2. **Progress** — a real stage list (fetch → transcript → quality → chunks → index) with counts,
   not a spinner. Long stages show throughput (`142 / 640 cues`, `12.4 min of audio / 60`).
3. **Review** — §2.4: quality numbers, flagged segments, replace-all, "Index this course",
   "Re-transcribe with Whisper" (when available), "Discard".
4. **Manage courses** — rename, delete (removes only that course's directory), re-index after a
   glossary fix, and a visible marker for *machine transcript* vs *creator subtitles*.

The existing `/api/profiles` payload already carries `name`, `ready`, `chunks`; it gains
`source`, `reviewed`, `duration`, and `user_created` so the sidebar can tell a user course from a
bundled one without a second request.

---

## 6. Failure modes to handle explicitly

| Failure | Handling |
|---|---|
| No subtitle track and no Whisper available | Offer the Whisper download (or explain plainly without it); never index an empty transcript |
| HTTP 429 / rate limit (measured above) | Pin languages (`en,en-US,en-orig`), retry once with backoff, then surface "YouTube is rate-limiting, try in a few minutes" |
| Private, members-only, age-restricted, or geo-blocked video | Clear message naming the reason yt-dlp gave; no partial course left behind |
| Playlist or channel URL pasted | Refuse with "paste one lecture, not a channel" (YAGNI — see §9) |
| Long video (2 h+) | Warn before starting with an estimated time; require confirmation for the Whisper path |
| Disk space | Check free space before transcription; state the requirement in the error |
| Machine sleeps mid-job | Job persists; on next launch the app offers **resume** or **discard** |
| yt-dlp goes stale (YouTube changes) | Freshest version at build time + "Update downloader" action that installs a newer pure-Python `yt_dlp` into the state dir and reloads it; the app never needs a rebuild for that |
| User closes the window mid-job | Same as sleep: job state is on disk, partial dir is deleted unless resumed |

**Terms-of-service note, stated honestly:** downloading YouTube content is against YouTube's
Terms unless the rights holder allows it, and caption-only fetching is the mildest form of it.
The feature is built for the user's own lectures and openly licensed material; the plan does not
pretend otherwise. Local-file ingest (Open Question 3) is the ToS-free path and shares 100 % of
the pipeline after `fetch.py`.

---

## 7. How this batch is verified

There is no CI in this repo (no `.github/`), so every gate below is run by hand and its output
recorded — the same rule `app-plan.md` sets for Batches 0–4.

**Baseline that must stay green** (measured today): `python -m pytest tests/ -q` → 52 passed;
`cd frontend && node scripts/quiz.check.ts && node scripts/sources.check.ts &&
node scripts/stream-text.check.ts` → three `ok` lines; `python packaging/verify_artifacts.py` →
8/8. A task that touches Python runs pytest; a task that touches UI behaviour runs the node
checks.

**New automated tests this batch owes** (offline — no network, no YouTube, so they stay
deterministic):

- `tests/test_subs.py` — VTT/SRT parsing against **committed fixtures**: one clean creator track
  and one auto-caption fragment with rolling cues; assert dedupe, segment order, and that
  timestamps survive round-trip.
- `tests/test_quality.py` — coverage/cue-duration/rolling/punctuation scoring, including a
  deliberately truncated track that must be flagged low quality.
- `tests/test_glossary.py` — near-miss matching (`Shaw's → Shor's`) with the false-positive cases
  that matter (`shot` must not match `Shor`, possessives and case must not break the match).
- `tests/test_registry.py` — slug rules, name collisions, bundled-vs-user precedence, and that a
  missing index marks a course `ready: false` rather than crashing the sidebar.
- `tests/test_jobs.py` — atomic publish (interrupt mid-job leaves no course directory and no
  temp dir), cancellation between batches, and resume-from-disk state.

The network path is verified **once per relevant task, by hand** (5.2, 5.6, 5.8, 5.9) and its
numbers written into `packaging/smoke.md` — a stubbed fetch proves the code runs, not that
YouTube still answers.

## 8. Tasks

- [ ] **5.1 Course registry** — `ingest/registry.py`: bundled + user courses, slug rules,
      collision handling, `resolve(name)`; `rag_chat.set_profile()` and `/api/profiles` use it.
      **Done when:** the three bundled courses still load and answer, a fake course placed in
      `state_dir/courses/demo/` (index + metadata copied from `quantum`) appears in the sidebar
      and answers a quantum question with correct timestamps.

- [ ] **5.2 Fetch + captions (no audio)** — `fetch.py`, `subs.py`: metadata, track selection with
      the ladder, pinned languages, VTT → segments, rolling-cue dedupe, quality signals.
      **Done when:** for two real lectures, one with creator subs and one with only auto-captions,
      the app stores `subtitles/<lang>.vtt` + `transcript.json`, and the printed quality summary
      matches a hand-check of the first/last minutes (timestamps within 2 s).

- [ ] **5.3 Chunk + embed from a transcript** — extract `chunk.py`/`embed.py` from the scripts,
      profile-agnostic; `chunk_transcripts.py` and `create_embeddings.py` become wrappers.
      **Done when:** `python chunk_transcripts.py --profile quantum` and the in-app path produce
      identical chunk counts and identical `metadata.pkl` on the same transcript.

- [ ] **5.4 Jobs + progress API** — `jobs.py`, `/api/ingest` endpoints, SSE stage events,
      cancellation, resume-after-restart, atomic publish.
      **Done when:** a job visibly advances through all stages in the UI; cancelling mid-embed
      leaves no course and no temp dir; killing the app mid-job offers resume on next launch.

- [ ] **5.5 Review screen** — quality numbers, flagged terms, replace-all, index/discard, and the
      `reviewed` flag recorded.
      **Done when:** a course with a seeded glossary near-miss (`Shaw's`) shows the flag, the
      replace-all fixes every occurrence, the course indexes, and a search for `Shor` then
      retrieves the corrected segment.

- [ ] **5.6 Whisper path** *(scope depends on Open Question 2)* — `audio.py`, `transcribe.py`,
      confidence flags, model download with progress, disk check.
      **Done when:** a video with no subtitle track produces a transcript on the installed build;
      measured wall-clock per hour of audio is recorded in `decisions.md`.

- [ ] **5.7 Course management** — rename/delete/re-index, machine-vs-creator marker.
      **Done when:** deleting a user course removes exactly its directory (verified by listing
      before/after) and leaves settings, other courses and chat history untouched.

- [ ] **5.8 Packaging** — bundle `ingest/`, un-exclude the modules the app now runs, add `yt_dlp`
      to the spec, wire `hades.ico`-style data rules for any new assets.
      **Done when:** `packaging/verify_artifacts.py` grows a check for the ingest modules and the
      frozen app ingests a lecture end to end; installer size delta is recorded in `BUILD.md`.

- [ ] **5.9 Acceptance test on the installed app** — the real gate for this batch.
      **Done when:** on the **installed** build, from a fresh state dir: paste one lecture link
      (≥ 1 h), review, index, ask two questions whose answers must come from that lecture, and
      both citations open the right minute. Numbers recorded: wall-clock per stage, final course
      size on disk, chunk count, and the transcript source used.

---

## 9. Out of scope (YAGNI, deliberately)

- Playlist/channel bulk ingest and scheduled refreshes.
- Non-English course UI (English tracks only in v1; translated tracks exist but indexing a
  translation doubles the corpus for little gain).
- Cloud transcription, accounts, sharing courses between machines.
- Re-transcribing the three bundled courses; they stay frozen.
- An LLM rewrite pass over transcripts (§2.3 explains why this is refused, not deferred).
- PDF/slide ingest — a different extractor, a different beast; if it happens, it is Batch 6.

---

## 10. Decisions to record in `decisions.md` when this runs

1. **Captions before Whisper** (if Open Question 2 answers "captions first"): seconds instead of
   minutes, ~20 MB instead of ~250 MB, at the cost of ASR-quality text — mitigated by §2.
2. **PyAV instead of bundling ffmpeg.exe** — one fewer binary to keep patched, ~70–100 MB saved,
   and `av` is already a dependency of the ingest scripts.
3. **Courses in the state dir, never the install dir** — the uninstaller must not eat user work.
4. **Two-phase publish (review → index)** — because an unchecked transcript is exactly the risk
   this batch is accused of ignoring.
5. **Transparent source labelling** — the sidebar tells the user whether a course rests on
   creator subtitles, auto-captions or Whisper.

---

## 11. Open questions — answer before task 5.1

1. **No-subtitle ladder:** when a video has neither creator subs nor usable auto-captions, should
   the app (a) offer the Whisper path, (b) refuse with an explanation, or (c) index the
   auto-captions anyway with a visible "machine transcript" warning? *(Recommend a, with c the
   fallback when `av`/Whisper is unavailable.)*
2. **Whisper availability:** bundle `faster-whisper` (+~180–250 MB installer), download it on
   demand the first time it is needed (smaller installer, one extra network step), or omit it
   entirely in v1 and ship captions only? *(Recommend download-on-demand with `base`.)*
3. **Local files:** should the same page accept a dropped `.mp4/.mp3` (no YouTube involved, no
   ToS question) in v1, or is that a later batch? *(`process_video.py` shows the pattern; the rest
   of the pipeline is identical.)*
4. **Length ceiling:** warn-and-confirm above what runtime — 1 h, 2 h, 3 h? *(Recommend 1 h for
   the Whisper path, no ceiling for captions.)*
5. **Whisper model size when downloaded:** `base` (142 MB, faster, weaker on proper nouns) or
   `small` (466 MB, what the existing courses used via `config.WHISPER_MODEL`)? *(Recommend
   `small`, since §2 shows proper nouns are exactly where it matters — but that is a 466 MB
   download on the user's connection.)*
