# checkup_timestamps.py — HadeS timestamp audit
# ==============================================================================
# Answers "is the timestamp it gives me actually where the video teaches this?"
# for many topics at once, instead of one question at a time.
#
# Ground truth = the real YouTube chapter markers in chapters.json (pulled from
# each video's description). Those are the timestamps the learner sees, so they
# are what the app's answer should land on.
#
# For every topic it runs the REAL pipeline (dense + rerank + time-cluster +
# curator) under three query forms — the bare word, the plural a learner
# actually types, and a real question — then reports which chapter the app
# pointed at versus the chapter that actually teaches the topic.
#
# Usage:
#   python checkup_timestamps.py --profile quantum
#   python checkup_timestamps.py --profile hades_demo --topics function requests loops
#   python checkup_timestamps.py --profile quantum --no-llm      # skip the Ollama curator
#   python checkup_timestamps.py --profile quantum --detail qubit
#
# Read-only: loads index/metadata, never writes to chunks/ or profiles/.
import argparse, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import rag_chat

CHAPTERS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chapters.json")
NEAR_SEC = 60  # hand-authored chapter markers are loose; treat +/-60s as on target

# --- default topic lists per profile -----------------------------------------
TOPICS = {
    "quantum": [
        "qubit", "superposition", "entanglement", "hadamard gate", "cnot gate",
        "bloch sphere", "measurement", "quantum fourier transform", "shor's algorithm",
        "deutsch-jozsa algorithm", "probability amplitude", "pauli matrices",
    ],
    "hades_demo": [
        "function", "variable", "list", "dictionary", "set", "loop", "string",
        "requests library", "virtual environment", "api key", "token", "class",
        "error handling", "json",
    ],
}

# Which chapter the video actually teaches each topic in, asserted by hand so every
# verdict is auditable (substring-guessing picks 'Setting Up VS Code' for 'set').
# None = this video has no dedicated chapter for the topic; the audit then only
# reports what the app cited instead of scoring it.
TOPIC_CHAPTER = {
    "quantum": {
        "qubit": "1.1 Introduction to Qubit",
        "superposition": "1.1 Introduction to Qubit",
        "entanglement": "2.5 Quantum Entanglement",
        "hadamard gate": "1.6 The Hadamard Gate",
        "cnot gate": "2.3 Multi-Qubit Gates",
        "bloch sphere": "1.3 Representing a Qubit on the Bloch Sphere",
        "measurement": "2.4 Measuring Singular Qubits",
        "quantum fourier transform": "3.6 Quantum Fourier Transform",
        "shor's algorithm": "3.8 Shor's Algorithm",
        "deutsch-jozsa algorithm": "3.4 Deutch-Jozsa Algorithm",
        "probability amplitude": None,   # taught throughout 1.1-1.2, no single chapter
        "pauli matrices": None,          # the video never uses the name
    },
    "hades_demo": {
        "function": "Functions (Defining & Calling)",
        "variable": "Variables",
        "list": "Lists",
        "dictionary": "Dictionaries",
        "set": "Sets",
        "loop": "Loops (For Loops & range())",
        "string": "Strings",
        "requests library": "Working with APIs (Requests Example)",
        "virtual environment": "Creating Virtual Environments (venv)",
        "class": "Introduction to Classes (OOP)",
        "error handling": "Error Handling (Try/Except)",
        "api key": None,                 # .env secrets vs the Requests chapter, ambiguous
        "token": None,
        "json": None,
    },
}


def query_forms(topic):
    """The word alone, the plural a learner actually types, and a real question."""
    forms = [("bare", topic), ("ask", f"what is a {topic}")]
    if not topic.endswith("s"):
        forms.insert(1, ("plural", topic + "s"))
    return forms


def fmt(sec):
    if sec is None:
        return "—"
    sec = int(round(float(sec)))
    h, sec = divmod(sec, 3600)
    m, s = divmod(sec, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


class ChapterBook:
    def __init__(self, rows):
        self.rows = sorted((int(a), b) for a, b in rows)

    def index_at(self, sec):
        """Index of the chapter a timecode falls in."""
        if sec is None:
            return None
        s = float(sec)
        idx = None
        for i, (start, _) in enumerate(self.rows):
            if s >= start:
                idx = i
            else:
                break
        return idx

    def title(self, idx):
        return self.rows[idx][1] if idx is not None and 0 <= idx < len(self.rows) else "—"

    def index_of_title(self, frag):
        for i, (_, title) in enumerate(self.rows):
            if frag.lower() in title.lower():
                return i
        return None


def load_book(profile):
    with open(CHAPTERS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    entry = data.get(profile)
    if not entry:
        return None, None
    return ChapterBook(entry["chapters"]), entry


def run(profile, topics, use_llm, detail=None, show_forms=True):
    rag_chat.set_profile(profile)
    book, entry = load_book(profile)
    if not book:
        print(f"  ! no chapters for '{profile}' in {CHAPTERS_PATH}")
        return []
    gate = getattr(config, "MIN_RETRIEVAL_CONFIDENCE", 0.35)
    print(f"\n{'='*118}")
    print(f"PROFILE {profile}  |  {entry['title']}  |  {entry['video']}  |  {fmt(entry['duration_sec'])}")
    print(f"curator={'LLM (Ollama)' if use_llm else 'heuristic fallback'}   refusal gate cos>={gate}")
    print(f"{'='*118}")
    if show_forms:
        head = (f"{'topic':<28}{'form':<7}{'app says':<20}{'chapters':<12}"
                f"{'should be':<44}{'verdict':<12}")
        print(head)
        print("-" * 122)
    out = []
    for t in topics:
        frag = TOPIC_CHAPTER.get(profile, {}).get(t)
        exp = book.index_of_title(frag) if frag else None
        exp_title = (f"#{exp+1} {fmt(book.rows[exp][0])} {book.title(exp)}"
                     if exp is not None else "(no chapter covers this topic)")
        for form, q in query_forms(t):
            try:
                r = rag_chat.search_chunks_curated(q, use_llm=use_llm)
            except Exception as e:
                print(f"{t:<24}{form:<7}ERROR {e}")
                continue
            main = r.get("main") or []
            conf = rag_chat.curated_confidence(r)
            if not main:
                print(f"{t:<24}{form:<7}(nothing retrieved)")
                continue
            starts = [m.get("start") for m in main]
            idxs = [book.index_at(s) for s in starts]
            # chapter markers are authored by hand and are often a few seconds to a
            # couple of minutes loose, so a pick just outside the marker still counts
            exp_start = book.rows[exp][0] if exp is not None else None
            near = (exp_start is not None
                    and any(s is not None and abs(float(s) - exp_start) <= NEAR_SEC for s in starts))
            if exp is None:
                v = "NO-CHAPTER"
            elif exp in idxs:
                v = "HIT" if idxs[0] == exp else "HIT(2nd)"
            else:
                # distance from the chapter marker to the pick that came closest
                off = int(float(min((s for s in starts if s is not None),
                                    key=lambda s: abs(float(s) - exp_start))) - exp_start)
                v = f"NEAR {off:+d}s" if near else f"WRONG {off/60:+.1f}m"
            if conf < gate:
                v += " refused"
            print(f"{t:<28}{form:<7}{', '.join(fmt(s) for s in starts[:3]):<20}"
                  f"{', '.join('#'+str(i+1) for i in idxs[:3]):<12}{exp_title[:42]:<44}{v:<12}")
            out.append({"topic": t, "form": form, "query": q, "starts": starts,
                        "chapters": [book.title(i) for i in idxs], "expected": exp,
                        "verdict": v, "conf": conf, "curated": r})
    if detail:
        for row in out:
            if row["topic"] != detail or row["form"] != "bare":
                continue
            print(f"\n--- top retrieved chunks for '{row['query']}' ---")
            for i, c in enumerate(row["curated"].get("raw_cands", [])[:5]):
                ch = book.title(book.index_at(c["start"]))
                print(f"  [{i+1}] {fmt(c['start'])}  cos={c['score']:.3f}  chapter={ch}")
                print(f"      {c['text'][:200].replace(chr(10), ' ')}")
    return out


def summarise(rows, book):
    if not rows:
        return
    scored = [r for r in rows if not r["verdict"].startswith("NO-CHAPTER")]
    unscored = [r for r in rows if r["verdict"].startswith("NO-CHAPTER")]
    print(f"\n{'='*118}\nSCORE BY QUERY FORM")
    print(f"{'='*118}")
    print(f"  ran {len(rows)} queries over {len({r['topic'] for r in rows})} topics: "
          f"{len(scored)} scored, {len(unscored)} unscored (no chapter to score against)")
    forms = sorted({r["form"] for r in rows})
    for form in forms:
        # startswith, not ==: a refused unscored row reads "NO-CHAPTER refused" and would
        # otherwise survive the filter and inflate the denominator with topics that have
        # no chapter to score against.
        vs = [r for r in rows if r["form"] == form and not r["verdict"].startswith("NO-CHAPTER")]
        if not vs:
            continue
        first = sum(1 for r in vs if r["verdict"].startswith(("HIT", "NEAR")) and r["verdict"] != "HIT(2nd)")
        any_hit = sum(1 for r in vs if r["verdict"].startswith(("HIT", "NEAR")))
        print(f"  {form:<8} first MAIN on the right chapter {first}/{len(vs)}    any MAIN {any_hit}/{len(vs)}")
    wrong = [r for r in rows if r["verdict"].startswith(("WRONG", "NEAR"))]
    if wrong:
        print(f"\n  OFF-TARGET PICKS ({len(wrong)}) [NEAR = within {NEAR_SEC}s of the chapter marker]:")
        for r in wrong:
            exp = (f"#{r['expected']+1} {book.title(r['expected'])}") if r["expected"] is not None else "?"
            chs = {}
            for s, c in zip(r["starts"], r["chapters"]):
                chs.setdefault(c, fmt(s))
            landed = "; ".join(f"{v} {k[:34]}" for k, v in chs.items())
            print(f"    {r['verdict']:<16}{r['topic']:<22}{r['form']:<8}{landed:<48} should be {exp[:34]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="quantum", choices=config.AVAILABLE_PROFILES)
    ap.add_argument("--topics", nargs="*", default=None, help="override the default topic list")
    ap.add_argument("--no-llm", action="store_true", help="skip the Ollama curator (heuristic fallback)")
    ap.add_argument("--detail", default=None, help="dump retrieved chunks for one topic")
    args = ap.parse_args()

    topics = args.topics or TOPICS.get(args.profile, [])
    if not topics:
        print(f"No default topics for profile '{args.profile}' — pass --topics")
        return
    book, _ = load_book(args.profile)
    rows = run(args.profile, topics, use_llm=not args.no_llm, detail=args.detail)
    if book:
        summarise(rows, book)


if __name__ == "__main__":
    main()
