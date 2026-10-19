"""No machine-specific paths anywhere in the Python sources (plan A1 + G1).

The plan found the author's username/paths hardcoded in rag_chat.py (A1) and
transcribe_parts.py (G1, guarded by os.path.exists so it failed silently). This
gate fails if either creeps back, in any top-level module.

Run:  python -m pytest tests/test_no_machine_paths.py -q
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
# "C:.Users" matches both C:/Users and C:\Users without escaping games.
PATTERN = re.compile(r"kingh|anaconda3|C:.Users", re.IGNORECASE)


def test_python_sources_have_no_machine_paths():
    hits = []
    for p in sorted(ROOT.glob("*.py")):
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if PATTERN.search(line):
                hits.append(f"{p.name}:{i}: {line.strip()[:90]}")
    assert hits == [], "machine-specific paths found:\n" + "\n".join(hits)


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main([__file__, "-q"]))
