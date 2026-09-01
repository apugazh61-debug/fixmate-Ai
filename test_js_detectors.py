"""
Tests for JavaScript Detectors & Engine Language Routing.

Verifies:
1. JS Missing Import Detector (CommonJS require generation).
2. JS Syntax Error Detector (Parenthesis balance & node --check validation).
3. JS Undefined Variable Detector (Scope analysis & fuzzy typo repair).
4. Adversarial cases (no false positives on arrow functions, closures, destructuring, template literals).
5. Clean degradation when Node is not installed.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

from core.detectors.javascript import (
    JsMissingImportDetector,
    JsSyntaxErrorDetector,
    JsUndefinedVariableDetector,
    is_node_available,
)
from core.engine import detect_language, run_local_pipeline


def test_language_detection():
    print("\n--- Test: Language detection routing ---")
    assert detect_language("const x = 10; console.log(x);") == "javascript"
    assert detect_language("function calc(a, b) { return a + b; }") == "javascript"
    assert detect_language("", file_path="server.js") == "javascript"
    assert detect_language("def add(a, b):\n    return a + b\n") == "python"
    assert detect_language("", file_path="main.py") == "python"
    print("  Language detection heuristics verified.")
    print("  PASS")


def test_js_missing_import():
    print("\n--- Test: JS Missing Import Detector ---")
    code = "function read(p) { return fs.readFileSync(p, 'utf8'); }"
    detector = JsMissingImportDetector()
    issues = detector.detect(code)
    assert len(issues) == 1
    assert "fs" in issues[0].message

    fix = detector.fix(code, issues)
    assert "const fs = require('fs');" in fix.fixed_code
    print("  Successfully detected and generated require('fs').")
    print("  PASS")


def test_js_syntax_error():
    print("\n--- Test: JS Syntax Error Detector ---")
    code = "function test(items) {\n    for (const item of items {\n        console.log(item);\n    }\n}"
    detector = JsSyntaxErrorDetector()
    issues = detector.detect(code)
    assert len(issues) >= 1
    assert "Missing closing parenthesis" in issues[0].message

    fix = detector.fix(code, issues)
    assert "for (const item of items) {" in fix.fixed_code
    print("  Successfully repaired unclosed for-loop parenthesis.")
    print("  PASS")


def test_js_undefined_variable():
    print("\n--- Test: JS Undefined Variable Detector ---")
    code = "function getFull(firstName, lastName) {\n    const full = `${firstName} ${lastName}`;\n    return ful;\n}"
    detector = JsUndefinedVariableDetector()
    issues = detector.detect(code)
    assert len(issues) == 1
    assert "ful" in issues[0].message
    assert "full" in issues[0].message

    fix = detector.fix(code, issues)
    assert "return full;" in fix.fixed_code
    print("  Successfully corrected typo ful -> full.")
    print("  PASS")


def test_js_adversarial_no_false_positives():
    print("\n--- Test: Adversarial constructs (arrow functions, destructuring, template literals) ---")
    code = """
    const processData = ({ id, value = 0 }, multiplier) => {
        const doubled = value * multiplier;
        const msg = `Item ID: ${id} => ${doubled}`;
        return { id, doubled, msg };
    };
    """
    detector = JsUndefinedVariableDetector()
    issues = detector.detect(code)
    assert len(issues) == 0, f"False positives detected: {issues}"

    res = run_local_pipeline(code, language="javascript")
    assert len(res.issues) == 0
    assert res.verified is True
    print("  Clean modern JS constructs produced 0 false positives.")
    print("  PASS")


def test_node_graceful_degradation():
    print("\n--- Test: Graceful degradation when Node is not installed ---")
    with patch("core.detectors.javascript.syntax_error.is_node_available", return_value=False):
        code = "function f() { return 1; }"
        detector = JsSyntaxErrorDetector()
        issues = detector.detect(code)
        assert len(issues) == 0
        print("  Handled missing Node binary cleanly.")
    print("  PASS")


def main() -> int:
    try:
        test_language_detection()
        test_js_missing_import()
        test_js_syntax_error()
        test_js_undefined_variable()
        test_js_adversarial_no_false_positives()
        test_node_graceful_degradation()
        print("\n" + "=" * 60)
        print("ALL JAVASCRIPT DETECTOR TESTS PASSED")
        print("=" * 60)
        return 0
    except Exception as exc:
        print(f"\n!! JS DETECTOR TEST FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
