# HadeS — timestamp audit

Two questions, answered separately:

1. **Are the timecodes accurate?** (does `01:17:01` really show what the app says it shows?)
2. **Is the chosen timestamp a good lesson to point at?**

They have different answers: (1) is fine, (2) is where the bug is.

Reproduce: `python checkup_timestamps.py --profile quantum` (add `--no-llm` to skip the Ollama
curator, `--detail qubit` to dump the retrieved chunks).

## Ground truth used

`chapters.json` holds the **real YouTube chapter markers**, pulled from each video's description
with agent-browser. Those are the timestamps the learner actually sees, so they are the right thing
to judge against — the same standard `EVAL.md` already uses ("Pass = retrieved within ~90s of
YouTube chapter").

| profile | video | length | chapters |
|---|---|---|---|
| `quantum` | Quantum Computing Course – Math and Theory for Beginners (`tsbCSkvHhMo`) | 01:36:03 | 29 |
| `hades_demo` | Python for AI - Full Beginner Course (`ygXn5nV5qFc`) | 05:15:31 | 84 |

## Finding 1 — the timecodes themselves are correct (no offset)

The stored times are Whisper segment times, and they line up with the video:

- Video length `18931s` vs transcript end `18930.72s`; quantum `5763s` vs `5760.18s`.
- Transcript text at each chapter's start time matches that chapter's title:

| chapter marker | transcript at that second |
|---|---|
| `01:01:33 Variables` | "now it's time to get into one of the most fundamental concepts in all of programming" |
| `01:13:36 Strings` | "now let's continue to the next data types. And those are strings." |
| `00:34:00 Creating Virtual Environments (venv)` | "to create your first virtual environment in our own project that we're currently working on" |
| `02:05:51 Functions (Defining & Calling)` | "functions, which are used to create reusable blocks of code" |
| `02:01:37 Sets` | "so let's get into sets, the final data structure" |

So clicking a timestamp lands on the text the app quoted. Nothing is shifted.

## Finding 2 — the reported case reproduces exactly

Searching **`qubits`** on the quantum video (LLM curator on, i.e. the real app path):

```
MAIN  00:14:50 – 00:17:28 (3 chunks) cos=0.487   → chapter 1.1 Introduction to Qubit  ✔
MAIN  01:17:01 – 01:18:36 (2 chunks) cos=0.516   → chapter 3.6 Quantum Fourier Transform
ALSO  00:38:59 – 00:40:06 cos=0.464              → chapter 2.3 Multi-Qubit Gates
```

`01:17:01` is **80% of the way through a 1:36 video** — that is the "damn near end of the video"
report, confirmed. The second MAIN is the Fourier-transform section, which says "qubits" six times
per sentence ("the phase of the qubits", "the number of qubits", "the right qubit…").

Same topic, three phrasings — the form changes which chapter the **first** MAIN lands on:

| query | first MAIN | its chapter | right chapter? |
|---|---|---|---|
| `qubits` | 00:16:08 | 1.1 Introduction to Qubit | yes |
| `qubit` | 00:38:59 | 2.3 Multi-Qubit Gates | no |
| `what is a qubit` | 00:16:08 | 1.1 Introduction to Qubit | yes |

So the hunch is right *for this case*, and the mechanism is not "the app is broken" — a bare word
matches whichever chunk repeats that word most, and advanced recap-style sections repeat topic words
heavily. The definition chunk at `00:14:50` only scores 0.487 against 0.516 for the Fourier chunk.

## Finding 3 — phrasing helps, but not uniformly

Score = "does a MAIN pick land on the chapter that teaches the topic". `NEAR` = within 60s of the
marker (chapter markers are hand-authored and loose).

Coverage per sweep (one curator mode): **quantum 35 queries over 12 topics** (30 scored, 5 unscored)
and **hades_demo 41 queries over 14 topics** (32 scored, 9 unscored). Both sweeps were run under each
curator, so 152 retrieval runs in total. Unscored = the video has no chapter for that topic, so there
is nothing to score against.

Denominators are per form, and `class` ends in "s" so it gets a bare and a question form but no
plural — hence `/10` for that one row.

Heuristic curator (`--no-llm`):

| profile | form | first MAIN right | any MAIN right |
|---|---|---|---|
| quantum | `ask` | **8/10** | 9/10 |
| quantum | `bare` | 6/10 | 9/10 |
| quantum | `plural` | 7/10 | 9/10 |
| hades_demo | `ask` | 7/11 | 9/11 |
| hades_demo | `bare` | **8/11** | 8/11 |
| hades_demo | `plural` | 7/10 | 8/10 |

LLM curator (the real app path):

| profile | form | first MAIN right | any MAIN right |
|---|---|---|---|
| quantum | `ask` | 7/10 | 9/10 |
| quantum | `bare` | 7/10 | 9/10 |
| quantum | `plural` | 7/10 | 8/10 |
| hades_demo | `ask` | 7/11 | 8/11 |
| hades_demo | `bare` | 8/11 | 8/11 |
| hades_demo | `plural` | 7/10 | 8/10 |

The LLM curator flattens the quantum gap (it drops the correct second pick more often) and makes
`superposition` worse — see below.

Read: on the quantum course a real question clearly beats a bare word for the *first* pick. On the
Python course it's a wash (bare edges it). **Phrasing is not a general fix — it's a nudge that helps
single-token topics on some corpora.**

## Every off-target pick found

quantum (LLM curator):

```
WRONG +45.2m  superposition   bare, plural  01:00:11 3.3 Deutsch's Algorithm; 01:06:12 3.4 Deutch-Jozsa  should be 1.1 Introduction to Qubit
WRONG +32.2m  superposition   ask           00:47:10 2.6 Phase Kickback; 01:06:12 3.4 Deutch-Jozsa       should be 1.1 Introduction to Qubit
WRONG -3.4m   measurement     plural        00:18:18 1.1 Introduction to Qubit; 00:37:27 2.2 Circuits    should be 2.4 Measuring Singular Qubits
NEAR  -10s    deutsch-jozsa   all forms     01:02:56 3.3 Deutsch's Algorithm                           should be 3.4 Deutch-Jozsa Algorithm
```

`superposition` is the worst case in the whole audit, and the LLM curator causes it: all three
phrasings point tens of minutes late (`+45.2m`, `+45.2m`, `+32.2m`) and **none** reach chapter 1.1
where superposition is actually defined. The bare word and the question are both wrong here, which is
what makes this a curation failure rather than a phrasing one.

```
'superposition'           conf=0.513  MAIN 60.2min 3.3 Deutsch's Algorithm; 66.2min 3.4 Deutch-Jozsa
'superpositions'          conf=0.518  MAIN 60.2min 3.3 Deutsch's Algorithm; 54.9min 3.2.B Functions
'what is a superposition' conf=0.494  MAIN 47.2min 2.6 Phase Kickback;    66.2min 3.4 Deutch-Jozsa
```

The heuristic fallback gets this right (`HIT` via the 00:15:31 pick), so the LLM curator is
removing the correct cluster rather than the retriever failing to find it.

hades_demo:

```
WRONG -3.1m   list             bare      01:50:24 Loops                                    should be Lists @ 01:53:32
WRONG -2.2m   dictionary       all forms 01:56:54 Lists                                    should be Dictionaries @ 01:59:10
WRONG -3.7m   loop             all forms 01:43:31 Conditional Statements                   should be Loops @ 01:47:11
WRONG -5.2m   requests library ask       00:41:26 Installing Python Packages (pip install) should be Working with APIs @ 02:56:04
NEAR  -6s     string           all forms 01:13:29 Numbers (Integers & Floats)              should be Strings @ 01:13:36
NEAR  -15s    set              ask       02:01:22 Tuples                                   should be Sets @ 02:01:37
```

`string` and `set` are 6s and 15s early — chapter-boundary artifacts, effectively correct. The real
misses are `list`, `dictionary`, `loop`, and `superposition`.

Two topics get a confident timestamp even though the video has no such lesson — the refusal gate
(`cos >= 0.35`) does not catch them:

- `pauli matrices` → cites `0.3 Introduction to Matrices` / `0.5 Unitary and Hermitian Matrices`
  (cos 0.406 / 0.422). The video never uses the name "Pauli".
- `json` → cites `Working with APIs (Requests Example)` (cos 0.451). JSON is mentioned, never taught.

`token` correctly refuses (cos 0.262 / 0.287).

## Root cause (where the fix goes)

In `rag_chat.search_chunks_curated` → `_cluster_by_time` → `_teaching_score` → `_ordered_main_clusters`:

1. `_search_with_scores` embeds the query as-is. A one-word query has almost no semantic content, so
   cosine is dominated by **how often the word appears** in a chunk. The dense-mention Fourier chunk
   wins on that basis alone.
2. `_teaching_score` uses `max_score` (cosine) as its base and only adds a `+0.12` bonus when the
   chunk contains the literal word "define"/"definition". The Fourier chunk beats the definitional
   cluster by ~0.05 cosine and never says "define", so the bonus never fires and the ordering stands.
3. `_ordered_main_clusters` correctly keeps the strong top-1 first (`MAIN_PRIOR_MIN_COSINE = 0.5`),
   but the second MAIN is then chosen purely by teaching score — which is how `01:17:01` becomes a
   "★ Main Lesson".

## Candidate fixes, cheapest first

- **Query expansion for 1–2 token queries.** If the query has no question word and ≤2 tokens,
  embed `"what is a {q}"` instead. Directly tested by the `ask` column: quantum first-MAIN goes
  6/10 → 8/10. Smallest change, measurable, no re-index.
- **Chapter-aware retrieval.** The chapter titles are already a perfect topical map
  (`chapters.json`) — indexing them as extra documents, or boosting a chunk whose enclosing chapter
  title matches the query, would make a bare `superposition` resolve to chapter 1.1.
- **Mention-density penalty / definition boost.** Penalise chunks where the query term repeats many
  times with no definitional cue nearby, and raise the definition bonus above the typical cosine gap
  (~0.05) it currently fails to clear.

Any of these changes ranking, so re-run `EVAL.md`'s 11 questions before and after —
`python tests/test_retrieval.py` covers the retrieval helpers.
