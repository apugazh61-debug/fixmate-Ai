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
from core import github_integration
from core import sandbox
from core import test_generator
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
if "github_repo" not in st.session_state:
    st.session_state.github_repo = "https://github.com/apugazh61-debug/fixmate-Ai"
if "github_token" not in st.session_state:
    st.session_state.github_token = ""
if "pr_result" not in st.session_state:
    st.session_state.pr_result = None

# ---------------------------------------------------------------- sidebar --
with st.sidebar:
    st.markdown("## 🛠️ FixMate AI")
    st.caption("Paste broken code. Get fixed code back — instantly.")

    st.markdown("### Example snippets")
    def _on_example_change():
        choice = st.session_state.get("example_choice_dropdown")
        if choice and choice != "— none —" and choice in EXAMPLES:
            st.session_state.code_input = EXAMPLES[choice]
            st.session_state.code_editor = EXAMPLES[choice]

    example_choice = st.selectbox(
        "Load a broken snippet",
        options=["— none —"] + list(EXAMPLES.keys()),
        index=0,
        key="example_choice_dropdown",
        on_change=_on_example_change,
        label_visibility="collapsed",
    )
    if example_choice and example_choice != "— none —":
        if st.button("🔄 Reload snippet", use_container_width=True):
            st.session_state.code_input = EXAMPLES[example_choice]
            st.session_state.code_editor = EXAMPLES[example_choice]
            st.rerun()

    st.divider()
    st.markdown("### Engine & Sandbox")
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

    docker_available, docker_reason = sandbox.get_availability_status()
    use_sandbox = st.toggle(
        "Verify in sandbox (Docker)",
        value=False,
        disabled=not docker_available,
        help="Run code inside an isolated python:3.12-slim container."
        if docker_available
        else f"Docker unavailable: {docker_reason}",
    )

    use_test_gen = st.toggle(
        "Generate test cases (Groq)",
        value=False,
        disabled=not config.settings.has_llm,
        help="Generate pytest test cases covering normal and edge cases."
        if config.settings.has_llm
        else "Requires Groq API key.",
    )

    engine_status = "🟢 Groq configured" if config.settings.has_llm else "⚪ Local engine only (offline)"
    sandbox_status = "🟢 Docker available" if docker_available else "⚪ Docker unavailable"
    st.caption(f"{engine_status}  ·  {sandbox_status}")

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
        result: AnalysisResult = run_pipeline(
            code_input,
            use_cloud_llm=use_cloud,
            error_message=error_message,
            verify_in_sandbox=use_sandbox,
            generate_tests=use_test_gen,
        )
    st.session_state.history.append(result)
    st.session_state.last_result = result
    st.session_state.pr_result = None

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

        tab_diff, tab_fixed, tab_sandbox, tab_trace = st.tabs([
            "Before / After", "Fixed code", "Sandbox & Tests", "Under the hood",
        ])

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
            fixed_editor = st.text_area(
                "Fixed code",
                value=result.fixed_code,
                height=260,
                key="fixed_code_viewer",
                help="You can review or fine-tune the fixed code here before downloading or opening a PR.",
            )
            # If user modified the code, record was_accepted=False
            if fixed_editor != result.fixed_code and "last_analytics_id" in st.session_state and st.session_state.last_analytics_id:
                analytics_store.update_acceptance(st.session_state.last_analytics_id, was_accepted=False)

            st.download_button(
                "⬇ Download fixed_code.py", data=fixed_editor,
                file_name="fixed_code.py", mime="text/x-python", use_container_width=True,
            )

        with tab_sandbox:
            st.markdown("##### 🐳 Docker Sandbox Verification")
            if result.sandbox_result:
                sr = result.sandbox_result
                if sr.runs_executed:
                    s1, s2 = st.columns(2)
                    with s1:
                        st.markdown(f"**Before:** {'🟢 Clean Run' if sr.before_ok else '🔴 Crashed / Error'}")
                        st.code(sr.before_output or "(no output)", language="text")
                    with s2:
                        st.markdown(f"**After:** {'🟢 Clean Run' if sr.after_ok else '🔴 Crashed / Error'}")
                        st.code(sr.after_output or "(no output)", language="text")
                else:
                    st.warning(f"Sandbox run unavailable: {sr.error}")
            else:
                st.caption("Sandbox verification was not enabled for this run. Enable 'Verify in sandbox' in the sidebar.")

            st.divider()
            st.markdown("##### 🧪 Auto-Generated Test Cases")
            if result.test_suite:
                ts = result.test_suite
                if ts.cases:
                    status_text = "🟢 All tests passed" if ts.all_passed else "⚠️ Some tests failed or need review"
                    st.markdown(f"**Status:** {status_text} ({len(ts.cases)} test cases generated)")
                    for case in ts.cases:
                        case_badge = "✅ Passed" if case.passed else "⚠️ Needs Review"
                        with st.expander(f"{case.name} — {case_badge}"):
                            if case.description:
                                st.caption(case.description)
                            st.code(case.code, language="python")
                            if case.output:
                                st.text(f"Output: {case.output}")
                elif ts.error:
                    st.warning(f"Test generation info: {ts.error}")
            else:
                st.caption("No unit tests generated. Enable 'Generate test cases (Groq)' in the sidebar.")

        with tab_trace:
            icon = {"ok": "✅", "warn": "⚠️", "fail": "❌", "info": "ℹ️"}
            for step in result.trace:
                st.markdown(f"{icon.get(step.status, '•')} **{step.name}** — {step.detail}")

        # ------------------------------------------------ Ship it Section --
        st.divider()
        with st.expander("🚀 Ship it — Open GitHub Pull Request", expanded=False):
            st.caption("Directly commit the fixed code to a new branch and open a PR back to the default branch.")

            # Safety Assessment Banner
            if result.safety_assessment:
                sa = result.safety_assessment
                sa_badge = "🔴 High Risk (Blocked)" if sa.blocks_pr else ("🟡 Medium Risk" if sa.level == "medium" else "🟢 Low Risk (Safe)")
                st.markdown(f"**Safety Gate:** `{sa_badge}` — Blast radius: {int(sa.blast_radius_score * 100)}%")
                if sa.blocks_pr:
                    st.error(f"⛔ **Auto-PR is Blocked by Safety Gate:** {'; '.join(sa.reasons)}")
                elif sa.level == "medium":
                    st.warning(f"⚠️ **Safety Gate Warning:** {'; '.join(sa.reasons)}")

            c_repo, c_tok = st.columns([1, 1])
            with c_repo:
                repo_url = st.text_input(
                    "GitHub Repository URL or owner/repo",
                    value=st.session_state.github_repo,
                    placeholder="https://github.com/apugazh61-debug/fixmate-Ai",
                )
            with c_tok:
                token_input = st.text_input(
                    "Personal Access Token",
                    type="password",
                    value=st.session_state.github_token,
                    help="GitHub PAT with 'repo' permissions. Never logged or saved to disk.",
                )

            file_path_input = st.text_input(
                "Target file path in repository",
                value="fixed_code.py",
                help="Path where the fixed code will be committed in the new branch.",
            )

            is_blocked = bool(result.safety_assessment and result.safety_assessment.blocks_pr)
            pr_button_disabled = not result.verified or is_blocked
            if is_blocked:
                pr_button_help = "Pull Request blocked by Safety Gate."
            elif not result.verified:
                pr_button_help = "Fix must be verified before opening a Pull Request."
            else:
                pr_button_help = "Open automated PR on GitHub"

            if st.button("🚀 Open Pull Request", type="primary", disabled=pr_button_disabled, help=pr_button_help, use_container_width=True):
                st.session_state.github_repo = repo_url
                st.session_state.github_token = token_input
                code_to_ship = st.session_state.get("fixed_code_viewer", result.fixed_code)
                with st.spinner("Creating branch, committing file, and opening PR on GitHub..."):
                    pr_result = github_integration.create_pull_request(
                        repo_input=repo_url,
                        token=token_input,
                        file_path=file_path_input,
                        fixed_code=code_to_ship,
                        explanation=result.explanation,
                        trace=result.trace,
                    )
                    st.session_state.pr_result = pr_result

            if st.session_state.pr_result:
                pr_res = st.session_state.pr_result
                if pr_res.success:
                    st.success(f"🎉 Pull Request created successfully! [#{pr_res.pr_number} — View on GitHub]({pr_res.pr_url}) on branch `{pr_res.branch_name}`")
                else:
                    st.error(f"❌ Failed to create Pull Request: {pr_res.error}")


if "last_result" in st.session_state:
    render_result(st.session_state.last_result)
else:
    with result_slot:
        st.caption("Paste some broken code on the left and click **Analyze & Fix** to see FixMate work.")

st.divider()
st.caption("FixMate AI · Developer Tools track · local engine runs fully offline, no API key required.")
