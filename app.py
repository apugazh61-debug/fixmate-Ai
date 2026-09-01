"""
FixMate AI — Streamlit front end.

Run with:  streamlit run app.py

The UI is a thin layer over core/engine.py. It never contains detection or
fix logic itself — it only renders whatever the pipeline returns, including
its step-by-step trace, so the "how it decided" story is visible, not just
the final answer.
"""

from __future__ import annotations

import difflib
import os

import streamlit as st

from core import config
from core.engine import run_pipeline
from core.models import AnalysisResult
from examples import EXAMPLES

st.set_page_config(
    page_title="FixMate AI",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------- session --
if "history" not in st.session_state:
    st.session_state.history = []  # list[AnalysisResult]
if "code_input" not in st.session_state:
    st.session_state.code_input = EXAMPLES["Undefined variable (typo)"]

# ---------------------------------------------------------------- sidebar --
with st.sidebar:
    st.markdown("## 🛠️ FixMate AI")
    st.caption("Paste broken code. Get fixed code back — instantly.")

    st.markdown("### Example snippets")
    example_choice = st.selectbox(
        "Load a broken snippet", options=["— none —"] + list(EXAMPLES.keys()), index=1,
        label_visibility="collapsed",
    )
    if example_choice != "— none —":
        if st.button("Load example", use_container_width=True):
            st.session_state.code_input = EXAMPLES[example_choice]
            st.rerun()

    st.divider()
    st.markdown("### Engine")
    api_key_input = st.text_input(
        "Groq API key (optional)", type="password",
        value=os.environ.get("GROQ_API_KEY", ""),
        help="Only needed to escalate beyond the 3 built-in local error classes. "
             "Get a free key at console.groq.com.",
    )
    if api_key_input:
        os.environ["GROQ_API_KEY"] = api_key_input
        config.settings = config.load_settings()

    use_cloud = st.toggle(
        "Escalate to cloud LLM when needed", value=False,
        help="The local engine runs first either way. This only kicks in if it finds nothing.",
    )

    engine_status = "🟢 Groq configured" if config.settings.has_llm else "⚪ Local engine only (offline)"
    st.caption(engine_status)

    st.divider()
    st.markdown("### What FixMate catches (offline)")
    st.markdown(
        "- Missing imports\n"
        "- Syntax errors — brackets, colons, indentation\n"
        "- Undefined variables (typos)"
    )

    if st.session_state.history:
        st.divider()
        st.markdown(f"### History ({len(st.session_state.history)})")
        for i, past in enumerate(reversed(st.session_state.history[-5:])):
            label = "✅ fixed" if past.verified else "⚠️ needs review"
            st.caption(f"{len(st.session_state.history) - i}. {label} · {past.source} · {len(past.issues)} issue(s)")

# ---------------------------------------------------------------- header --
st.title("FixMate AI")
st.markdown(
    "##### Paste broken code, get fixed code back — with a plain-English reason why it broke."
)

left, right = st.columns([1, 1], gap="large")

with left:
    st.markdown("#### Broken code")
    code_input = st.text_area(
        "Broken code", value=st.session_state.code_input, height=340,
        label_visibility="collapsed", key="code_editor",
    )
    error_message = st.text_input(
        "Paste the error message too, if you have it (optional)",
        placeholder="e.g. NameError: name 'item' is not defined",
    )
    run_clicked = st.button("🔍  Analyze & Fix", type="primary", use_container_width=True)

with right:
    st.markdown("#### Result")
    result_slot = st.container()

# ---------------------------------------------------------------- run it --
if run_clicked and not code_input.strip():
    with result_slot:
        st.warning("Paste some code first — the box on the left is empty.")
elif run_clicked and code_input.strip():
    st.session_state.code_input = code_input
    with st.spinner("Running detect → fix → verify pipeline..."):
        result: AnalysisResult = run_pipeline(code_input, use_cloud_llm=use_cloud, error_message=error_message)
    st.session_state.history.append(result)
    st.session_state.last_result = result

# ---------------------------------------------------------------- render --
def render_result(result: AnalysisResult) -> None:
    with result_slot:
        badge = "✅ Verified fix" if result.verified else "⚠️ Best-effort fix — please review"
        source_label = "Groq cloud LLM" if result.source == "groq_llm" else "Local engine (offline)"
        st.markdown(f"**{badge}**  ·  engine: `{source_label}`  ·  attempts: `{result.attempts}`")

        if result.issues:
            tags = " ".join(f"`{i.error_type.value}`" for i in result.issues)
            st.markdown(f"**Detected:** {tags}")
        else:
            st.markdown("**Detected:** no issues found")

        st.info(result.explanation)

        tab_diff, tab_fixed, tab_trace = st.tabs(["Before / After", "Fixed code", "Under the hood"])

        with tab_diff:
            d1, d2 = st.columns(2)
            with d1:
                st.caption("Original")
                st.code(result.original_code, language="python")
            with d2:
                st.caption("Fixed")
                st.code(result.fixed_code, language="python")

            diff_lines = list(difflib.unified_diff(
                result.original_code.splitlines(),
                result.fixed_code.splitlines(),
                lineterm="", fromfile="before", tofile="after",
            ))
            if diff_lines:
                with st.expander("Unified diff"):
                    st.code("\n".join(diff_lines), language="diff")

        with tab_fixed:
            st.code(result.fixed_code, language="python")
            st.download_button(
                "⬇ Download fixed_code.py", data=result.fixed_code,
                file_name="fixed_code.py", mime="text/x-python", use_container_width=True,
            )

        with tab_trace:
            icon = {"ok": "✅", "warn": "⚠️", "fail": "❌", "info": "ℹ️"}
            for step in result.trace:
                st.markdown(f"{icon.get(step.status, '•')} **{step.name}** — {step.detail}")


if "last_result" in st.session_state:
    render_result(st.session_state.last_result)
else:
    with result_slot:
        st.caption("Paste some broken code on the left and click **Analyze & Fix** to see FixMate work.")

st.divider()
st.caption("FixMate AI · Developer Tools track · local engine runs fully offline, no API key required.")
