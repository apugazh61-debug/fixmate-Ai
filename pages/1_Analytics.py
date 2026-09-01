"""
FixMate AI — Team Analytics Dashboard.

Streamlit multipage view showing issue-type frequency, recurring files,
and verification success rates recorded by the pipeline.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from core import analytics_store

st.set_page_config(
    page_title="FixMate AI · Analytics",
    page_icon="📊",
    layout="wide",
)

st.title("📊 FixMate AI Team Analytics")
st.markdown("##### Performance metrics, error class distribution, and recurring codebase hotspots.")

stats = analytics_store.get_summary_stats()

if stats["total_runs"] == 0:
    st.info("ℹ️ **No analytics recorded yet.**")
    st.caption(
        "Run code fixes on the main **FixMate AI** tab or via CI Webhooks to start accumulating telemetry data."
    )
else:
    # Top KPI metric cards
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Total Analysis Runs", stats["total_runs"])
    with m2:
        st.metric("Verified Fixes", stats["verified_count"])
    with m3:
        st.metric("Success Rate", f"{stats['verification_rate']}%")
    with m4:
        st.metric("Engine Split", f"{stats['local_runs']} local / {stats['groq_runs']} cloud")

    st.divider()

    c1, c2 = st.columns([1, 1], gap="large")

    with c1:
        st.markdown("#### 📉 Error Classes Frequency")
        err_freq = analytics_store.get_error_frequency()
        if err_freq:
            df_err = pd.DataFrame(
                list(err_freq.items()),
                columns=["Error Type", "Count"],
            ).set_index("Error Type")
            st.bar_chart(df_err)
        else:
            st.caption("No error categories recorded.")

    with c2:
        st.markdown("#### 🎯 Top Recurring Files / Hotspots")
        top_files = analytics_store.get_top_recurring_files(limit=5)
        if top_files:
            df_files = pd.DataFrame(top_files)
            df_files.columns = ["File Path", "Occurrences"]
            st.dataframe(df_files, use_container_width=True, hide_index=True)
        else:
            st.caption("No multi-file paths recorded yet (interactive editor fixes only).")

    st.divider()
    st.markdown("#### 📜 Recent Analysis History")
    history = analytics_store.get_recent_history(limit=20)
    if history:
        df_hist = pd.DataFrame(history)
        df_hist["verified"] = df_hist["verified"].apply(lambda v: "✅ Verified" if v else "⚠️ Review")
        df_hist.rename(
            columns={
                "id": "ID",
                "timestamp": "Timestamp",
                "repo_name": "Repo",
                "file_path": "File",
                "error_types": "Errors",
                "issue_count": "Issues",
                "verified": "Status",
                "source": "Engine",
                "attempts": "Attempts",
            },
            inplace=True,
        )
        st.dataframe(df_hist, use_container_width=True, hide_index=True)
    else:
        st.caption("No history records.")

st.divider()
st.caption("FixMate AI · SQLite Analytics Store · updates automatically on every pipeline run.")
