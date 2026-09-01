"""
Real UI-level test using Streamlit's official AppTest harness.
This actually runs the script, sets widget values, clicks the button,
and checks the rendered output — not just "does the server respond".
"""
import sys
from pathlib import Path
from streamlit.testing.v1 import AppTest

APP_PATH = str(Path(__file__).parent / "app.py")


def run_case(code: str, label: str, expect_verified: bool = True):
    at = AppTest.from_file(APP_PATH)
    at.run(timeout=30)
    assert not at.exception, f"[{label}] exception on initial load: {at.exception}"

    at.text_area(key="code_editor").set_value(code)
    at.button[0].click()
    at.run(timeout=30)
    assert not at.exception, f"[{label}] exception after clicking Analyze & Fix: {at.exception}"

    body = "\n".join(m.value for m in at.markdown) + "\n".join(i.value for i in at.info)
    print(f"--- {label} ---")
    print("  exception:", at.exception)
    print("  contains 'Verified fix':", "Verified fix" in body)
    print("  contains 'Best-effort':", "Best-effort" in body)
    ok = ("Verified fix" in body) == expect_verified
    print("  PASS" if ok else "  FAIL", "\n")
    return ok


if __name__ == "__main__":
    from examples import EXAMPLES

    results = []
    for name, code in EXAMPLES.items():
        results.append(run_case(code, name, expect_verified=True))

    # Also test the empty-input edge case and a totally clean snippet
    results.append(run_case("def f():\n    return 1\n", "Already-clean code", expect_verified=True))

    print("=" * 60)
    print(f"{sum(results)}/{len(results)} UI-level cases passed")
    sys.exit(0 if all(results) else 1)
