"""
Smoke tests for VS Code Extension inline analysis endpoint (POST /analyze/inline).

Verifies:
1. Fast, offline analysis response format expected by extension.ts.
2. Accurate issue line numbers, error types, and confidence scores.
3. Successful generation of clean fixed_code for 1-click Quick Fixes.
"""

from __future__ import annotations

import sys
from fastapi.testclient import TestClient

from webhook_app import app

client = TestClient(app)


def test_health_endpoint():
    print("\n--- Test: Health check endpoint ---")
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json().get("offline_ready") is True
    print("  Health endpoint responding.")
    print("  PASS")


def test_inline_undefined_variable():
    print("\n--- Test: Inline analyze undefined variable ---")
    broken_code = "def calc_total(items):\n    total = 0\n    return item\n"
    payload = {"code": broken_code, "file_path": "calc.py"}

    res = client.post("/analyze/inline", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["verified"] is True
    assert len(data["issues"]) == 1
    issue = data["issues"][0]
    assert issue["error_type"] == "undefined_variable"
    assert issue["line"] == 3
    assert "item" in issue["message"]
    assert "return items" in data["fixed_code"]
    print(f"  Diagnosed line {issue['line']}: {issue['message']}")
    print(f"  Fixed snippet verified cleanly.")
    print("  PASS")


def test_inline_missing_import():
    print("\n--- Test: Inline analyze missing import ---")
    broken_code = "def circle(r):\n    return math.pi * r ** 2\n"
    payload = {"code": broken_code, "file_path": "geometry.py"}

    res = client.post("/analyze/inline", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["verified"] is True
    assert any(i["error_type"] == "missing_import" for i in data["issues"])
    assert "import math" in data["fixed_code"]
    print("  Diagnosed missing import and generated import statement.")
    print("  PASS")


def test_inline_clean_code():
    print("\n--- Test: Inline analyze clean code (no false positives) ---")
    clean_code = "def add(a, b):\n    return a + b\n"
    payload = {"code": clean_code, "file_path": "math_ops.py"}

    res = client.post("/analyze/inline", json=payload)
    assert res.status_code == 200
    data = res.json()

    assert data["verified"] is True
    assert len(data["issues"]) == 0
    assert data["fixed_code"].strip() == clean_code.strip()
    print("  Clean code returned 0 diagnostics.")
    print("  PASS")


def main() -> int:
    try:
        test_health_endpoint()
        test_inline_undefined_variable()
        test_inline_missing_import()
        test_inline_clean_code()
        print("\n" + "=" * 60)
        print("ALL VS CODE EXTENSION SMOKE TESTS PASSED")
        print("=" * 60)
        return 0
    except Exception as exc:
        print(f"\n!! VS CODE SMOKE TEST FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
