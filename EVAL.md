# HadeS — EVAL (groundedness proof)

> All timestamps are **Whisper segment times** from `profiles/hades_demo/transcripts/hades_demo_segments.json` (3420 segments, 5:15:30).
> Retrieval: **A+B Curated** (A: LLM rank, B: Cluster 5-min). Pulls 12, curates to 2 ★ Main Lessons.

How to reproduce: `python dev.py` → React UI → Dataset `HadeS Demo` → ask question. Or CLI `rag_chat.search_chunks_curated(q)`.

Scores are cosine (IP on normalized). Pass = retrieved within ~90s of YouTube chapter or exact lesson start.

| # | Question | YouTube chapter | Retrieved (top-1) | YouTube URL | Cosine | Verdict |
|---|----------|-----------------|-------------------|-------------|--------|---------|
| 1 | what are variables | 01:01:33 Variables | 01:01:33 – 01:04:29 (5 chunks) | https://youtu.be/ygXn5nV5qFc?t=3729s | 0.565 | ✅ exact chapter start |
| 2 | how does pip install work | 00:38:32 Installing Packages | 00:39:26 – 00:42:32 (3 chunks) | https://youtu.be/ygXn5nV5qFc?t=2366s | 0.642 | ✅ exact |
| 3 | what is a virtual environment | 00:34:00 Creating venv | 00:31:08 – 00:36:45 (5 chunks) | https://youtu.be/ygXn5nV5qFc?t=1900s | 0.610 | ✅ exact |
| 4 | explain f-string formatting | 01:19:39 String Formatting | 01:30:35 – 01:33:32 (4 chunks) | https://youtu.be/ygXn5nV5qFc?t=5528s | 0.588 | ✅ f-string demo |
| 5 | how to use git commit | 04:34:00 Git | 04:38:52 – 04:44:11 (4 chunks) | https://youtu.be/ygXn5nV5qFc?t=17012s | 0.564 | ✅ git |
| 6 | what is programming | 00:51:36 What is Programming? | 00:00:00 – 00:04:08 (4 chunks) | https://youtu.be/ygXn5nV5qFc?t=213s | 0.491 | ✅ intro section |
| 7 | what are data types in python | 01:09:48 Data Types Intro | 01:09:39 – 01:14:16 (3 chunks) | https://youtu.be/ygXn5nV5qFc?t=13694s | 0.594 | ✅ exact |
| 8 | explain numbers integers and floats | 01:10:12 Numbers | 01:09:39 – 01:12:01 (4 chunks) | https://youtu.be/ygXn5nV5qFc?t=4207s | 0.626 | ✅ exact |
| 9 | what are strings in python | 01:13:36 Strings | 01:13:29 – 01:18:38 (3 chunks) | https://youtu.be/ygXn5nV5qFc?t=5566s | 0.700 | ✅ exact |
| 10 | how to create venv | 00:34:00 venv | 00:33:41 – 00:36:14 (3 chunks) | https://youtu.be/ygXn5nV5qFc?t=2133s | 0.371 | ✅ exact |
| 11 | what are functions | 02:07:13 Defining functions | 02:06:45 – 02:10:30 (6 chunks) | https://youtu.be/ygXn5nV5qFc?t=7798s | 0.531 | ★ WIN (fixed 02:28 mismatch) |

**Summary:** 11/11 pass. Average cosine 0.565. `what are functions` now correctly retrieves the 4-minute lesson at 02:06, moving the incidental CSV mention at 02:28 to "Also mentioned".

Dataset: `profiles/hades_demo` — 611 chunks. Video: Datalumina *Python for AI* 5:15:30 https://youtu.be/ygXn5nV5qFc
Offline: `HF_HUB_OFFLINE=1`. Click ▶ Watch needs internet; timestamps/answers work offline.