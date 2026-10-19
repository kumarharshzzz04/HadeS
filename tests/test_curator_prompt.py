"""Curator prompt must fit the course it curates (plan Task 0.6 / G17-G18).

The prompt used to hardcode Python-course examples ("02:06", "dog breed error")
and a code-shaped definition of TEACH for every profile — wrong on the quantum
course and biasing its picks.

Run:  python -m pytest tests/test_curator_prompt.py -q
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import rag_chat as rc  # noqa: E402


def _clusters():
    """Three clusters of one chunk each — enough for _llm_pick_main (needs > main_k)."""
    def chunk(text, start):
        return {"text": text, "label": f"L{int(start)}", "start": float(start),
                "end": float(start + 30), "score": 0.9, "part": 0}
    return [
        [chunk("A qubit is the quantum analogue of a classical bit. " * 4, 10)],
        [chunk("Superposition lets a qubit hold both states at once. " * 4, 400)],
        [chunk("Measurement collapses the state to a definite outcome. " * 4, 900)],
    ]


def _capture_prompt(monkeypatch):
    captured = {}
    monkeypatch.setattr(rc, "ask_llm", lambda prompt: captured.setdefault("prompt", prompt) or '{"main": [0, 1]}')
    return captured


def test_quantum_prompt_has_no_python_course_examples(monkeypatch):
    captured = _capture_prompt(monkeypatch)
    rc.set_profile("quantum")
    rc._llm_pick_main("what is a qubit", _clusters(), 2)
    prompt = captured["prompt"]
    assert "02:06" not in prompt
    assert "dog breed" not in prompt
    assert "CSV" not in prompt
    assert "with code example" not in prompt
    assert "Introduction to Qubit" in prompt


def test_python_course_prompt_keeps_its_examples(monkeypatch):
    captured = _capture_prompt(monkeypatch)
    rc.set_profile("hades_demo")
    rc._llm_pick_main("what are functions", _clusters(), 2)
    prompt = captured["prompt"]
    assert "02:06" in prompt and "dog breed" in prompt


def test_every_profile_has_a_prompt_that_still_asks_for_json(monkeypatch):
    captured = _capture_prompt(monkeypatch)
    for profile in rc.config.AVAILABLE_PROFILES:
        rc.set_profile(profile)
        rc._llm_pick_main("anything", _clusters(), 2)
        assert 'Return ONLY JSON' in captured["prompt"]


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main([__file__, "-q"]))
