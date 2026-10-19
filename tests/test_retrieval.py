"""Smallest runnable check for hybrid retrieval (BM25 + RRF + confidence).

Run:  python -m pytest tests/ -q        (or: python tests/test_retrieval.py)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rag_chat as rc  # noqa: E402


def test_tokenize_keeps_code_terms():
    assert rc._tokenize("Use f-string and pd.read_csv here!") == ["use", "f-string", "and", "pd.read_csv", "here"]


def test_bm25_ranks_exact_term_first():
    docs = [
        "variables store values in memory",
        "a function is a reusable block of code",
        "this csv file holds rows of data",
    ]
    scores = rc._bm25_scores(rc._bm25_stats(docs), "what is a function")
    assert max(scores, key=scores.get) == 1, scores


def test_rrf_prefers_docs_ranked_high_in_both_lists():
    # doc 7 is 1st dense / 3rd sparse; doc 9 is 2nd in both -> 7 must still win
    fused = rc._rrf_fuse([[7, 9, 4], [1, 9, 7]], k=60)
    assert fused[0] == 7 and fused[1] == 9, fused


def test_confidence_reads_main_and_also():
    curated = {"main": [{"score": 0.61}, {"score": 0.4}], "also": [{"score": 0.72}]}
    assert rc.curated_confidence(curated) == 0.72
    assert rc.curated_confidence({}) == 0.0


def test_confidence_includes_retrieved_pool():
    # the refusal gate must not flip with the curator's picks: a strong candidate
    # that curation dropped still counts as "this question is answerable"
    curated = {"main": [{"score": 0.2}], "also": [], "raw_cands": [{"score": 0.18}, {"score": 0.44}]}
    assert rc.curated_confidence(curated) == 0.44


class _FakeReranker:
    """Longer text scores higher — deterministic stand-in for the cross-encoder."""

    def predict(self, pairs):
        return [len(p[1]) for p in pairs]


def test_prior_cluster_leads_and_rest_sorted():
    c0 = {"text": "strings lesson", "score": 0.70, "start": 100, "end": 200, "part": "p"}
    c1 = {"text": "f-string syntax define", "score": 0.64, "start": 900, "end": 950, "part": "p"}
    c2 = {"text": "other lesson", "score": 0.30, "start": 5000, "end": 5050, "part": "p"}
    cands = [c0, c1, c2]
    clusters = rc._cluster_by_time(cands)
    out = rc._ordered_main_clusters("what are strings in python", cands, clusters, [clusters[1], clusters[0]], 2)
    assert out[0][0] is c0, out
    assert len(out) == 2


def test_prior_swapped_in_when_curator_dropped_it():
    c0 = {"text": "strings lesson", "score": 0.70, "start": 100, "end": 200, "part": "p"}
    c1 = {"text": "f-string syntax define", "score": 0.64, "start": 900, "end": 950, "part": "p"}
    c2 = {"text": "other lesson", "score": 0.30, "start": 5000, "end": 5050, "part": "p"}
    cands = [c0, c1, c2]
    clusters = rc._cluster_by_time(cands)
    out = rc._ordered_main_clusters("q", cands, clusters, [clusters[1], clusters[2]], 2)
    assert out[0][0] is c0 and len(out) == 2, out
    assert all(cl is not clusters[2] for cl in out)


def test_weak_top1_defers_to_teaching_order():
    junk = {"text": "mention of functions in passing", "score": 0.48, "start": 100, "end": 150, "part": "p"}
    good = {"text": "we define a function with def", "score": 0.42, "start": 900, "end": 950, "part": "p"}
    cands = [junk, good]
    clusters = rc._cluster_by_time(cands)
    out = rc._ordered_main_clusters("what are functions", cands, clusters, [clusters[0], clusters[1]], 2)
    assert out[0][0] is good, out


def test_rerank_reorders_and_caps():
    rc._reranker = _FakeReranker()
    try:
        cands = [{"text": "short"}, {"text": "much longer text here"}, {"text": "mid length"}]
        out = rc.rerank("q", cands, top_k=2)
        assert [c["text"] for c in out] == ["much longer text here", "mid length"], out
    finally:
        rc._reranker = None


if __name__ == "__main__":
    # This used to be a hand-maintained list and it had silently stopped running
    # test_confidence_includes_retrieved_pool, the refusal-gate regression test (G19).
    # pytest runs every test in the file; never rebuild the list.
    raise SystemExit(__import__("pytest").main([__file__, "-q"]))
