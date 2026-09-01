"""
Regression test for a real bug found during a full audit:

`engine.py`, `llm_client.py`, and `detectors/syntax_error.py` used to do
    from core.config import settings
which binds a *snapshot* of the Settings object at import time. Since
Streamlit caches imported modules across reruns, typing a Groq API key into
the sidebar (which does `config.settings = config.load_settings()`) never
reached those modules — they kept referencing the old, keyless object for
the lifetime of the process. The fix: those modules now do
`from core import config` and read `config.settings.xxx` at call time,
so they always see the live object.

This test drives the actual sidebar widget via Streamlit's AppTest harness
and fails loudly if the stale-binding bug ever comes back.
"""
import os
import sys

from streamlit.testing.v1 import AppTest


def main() -> int:
    from core import config

    os.environ.pop("GROQ_API_KEY", None)
    config.settings = config.load_settings()

    at = AppTest.from_file("app.py")
    at.run(timeout=30)
    assert not at.exception, f"exception on initial load: {at.exception}"
    before = config.settings.has_llm
    print("before entering key -> config.settings.has_llm:", before)

    key_widget = next(w for w in at.text_input if w.label == "Groq API key (optional)")
    key_widget.set_value("gsk_fake_test_key_1234567890")
    at.run(timeout=30)
    assert not at.exception, f"exception after entering key: {at.exception}"

    after = config.settings.has_llm
    print("after entering key  -> config.settings.has_llm:", after)

    ok = (before is False) and (after is True)
    print("REGRESSION TEST:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
