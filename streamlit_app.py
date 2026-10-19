"""HadeS desk — the basic front end that ships with this repository.

The retrieval core is untouched: this file only collects a question, calls
`rag_chat.search_chunks_curated` and `rag_chat.ask_llm`, and prints what comes back. The
prompt shape is the same one `server.py` uses, so the desk and the API answer alike.

    python -m streamlit run streamlit_app.py      (or: start_hades_ui.bat)

Needs: the `profiles/` indexes present and Ollama answering on :11434.
"""
from __future__ import annotations

import re
import time

import streamlit as st

import config
import rag_chat

st.set_page_config(page_title="HadeS — basic front end", page_icon="🎓", layout="centered")


def build_prompt(question: str, context: str, history: list[dict]) -> str:
    """Prompt shape copied from server.py (_build_prompt) — identical answers both ways."""
    hist = "\n".join(
        f"User: {h.get('question', '')}\nAssistant: {str(h.get('answer', ''))[:600]}"
        for h in history[-getattr(config, "CHAT_HISTORY_TURNS", 3):]
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


def clock(seconds) -> str:
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "—"
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def ollama_alive() -> bool:
    try:
        import requests
        return requests.get(config.OLLAMA_TAGS_URL, timeout=2).ok
    except Exception:                                     # any failure means "not answering"
        return False


profiles = [p for p in rag_chat.list_profiles() if p["ready"]]
if not profiles:
    st.error("No index found. Build one first: "
             "`python create_embeddings.py --profile <name>`")
    st.stop()

st.session_state.setdefault("history", [])

with st.sidebar:
    st.header("Lecture set")
    names = [p["name"] for p in profiles]
    default = names.index(config.DEFAULT_PROFILE) if config.DEFAULT_PROFILE in names else 0
    picked = st.selectbox("Dataset", names, index=default)
    info = next(p for p in profiles if p["name"] == picked)
    st.caption(f"{info['chunks']} chunks indexed · re-asks keep this set's history")

    alive = ollama_alive()
    st.caption(("Ollama answering" if alive else "Ollama not answering")
               + f" · model `{config.OLLAMA_MODEL_NAME}`")
    if not alive:
        st.warning("Start it first: `ollama serve`, then `ollama run "
                   f"{config.OLLAMA_MODEL_NAME}`", icon="⚠️")

    if st.button("Clear conversation"):
        st.session_state.history = []
        st.rerun()

st.title("HadeS")
st.caption("Ask anything about the indexed lectures. Every answer says where it came from.")

question = st.text_input("Question", placeholder="what is a variable?")

if st.button("Ask", type="primary") and question.strip():
    if st.session_state.get("profile") != picked:
        rag_chat.set_profile(picked)                      # reloads the FAISS index once
        st.session_state.profile = picked
        st.session_state.history = []                     # history belongs to one dataset

    try:
        with st.spinner("Searching transcripts → finding the exact lessons → composing the answer…"):
            started = time.time()
            curated = rag_chat.search_chunks_curated(
                question, use_llm=getattr(config, "LLM_CURATOR_ENABLED", True))
            confidence = rag_chat.curated_confidence(curated)

            declined = (getattr(config, "REFUSAL_ENABLED", False)
                        and confidence < getattr(config, "MIN_RETRIEVAL_CONFIDENCE", 0.0))
            if declined:
                answer = ("I couldn't find this in the indexed lectures. Try rephrasing, or "
                          "check whether the topic is covered in the current dataset.")
            else:
                answer = rag_chat.ask_llm(
                    build_prompt(question, curated.get("context", ""), st.session_state.history))
    except FileNotFoundError as exc:
        st.error(f"{exc} — run `python create_embeddings.py --profile {picked}`")
        st.stop()
    except Exception as exc:                              # keep the page usable
        st.error(f"{type(exc).__name__}: {exc}")
        st.stop()

    elapsed = time.time() - started
    if not answer.strip():
        st.warning("Ollama returned nothing. Is it running, and is the model pulled?")
        st.stop()

    st.markdown(answer)

    cited = list(curated.get("main", [])) + list(curated.get("also", []))
    if getattr(config, "GROUNDING_VALIDATION", False):
        try:
            check = rag_chat.validate_grounding(answer, cited)
            st.caption(f"grounding: {check.get('pass_ratio', '—')} of the answer is traceable "
                       f"to the cited lessons")
        except Exception:                                 # validation is optional
            pass

    main, also = curated.get("main", []), curated.get("also", [])
    if main:
        st.subheader("Where this is taught")
        for d in main:
            label = d.get("label") or "lesson"
            # the core's label usually already carries "00:12:34 – 00:15:02 (n chunks)";
            # only add the range when it does not, so the line reads once
            times = "" if re.search(r"\d\d:\d\d:\d\d", label) else \
                f" · {clock(d.get('start'))} – {clock(d.get('end'))}"
            watch = f" · [watch]({d['youtube_url']})" if d.get("youtube_url") else ""
            st.markdown(f"**{label}**{times}{watch}")
            snippet = (d.get("text") or "")[:300].strip()
            if snippet:
                st.caption(snippet + ("…" if len(d.get("text") or "") > 300 else ""))
    if also:
        with st.expander(f"Also mentioned — {len(also)} more passage(s)"):
            for d in also:
                st.markdown(f"- {clock(d.get('start'))} – {clock(d.get('end'))} · "
                            f"{(d.get('text') or '')[:200].strip()}…")

    st.caption(f"{len(cited)} passages considered · confidence {confidence:.2f} · "
               f"{elapsed:.1f}s" + (" · declined to answer" if declined else ""))

    st.session_state.history.append({"question": question, "answer": answer})

st.caption("Retrieval, curation and generation are `rag_chat.py` — this page only asks it. "
           "The full React UI (globe landing, in-page player, quizzes) is private.")
