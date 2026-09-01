"""
JavaScript Undefined Variable & Typo Detector.

Analyzes JavaScript declared scope variables (const, let, var, parameters, functions)
and matches undeclared identifier typos using difflib fuzzy matching.
"""

from __future__ import annotations

import difflib
import re

from core.detectors.base import Detector
from core.models import ErrorType, Fix, Issue


JS_BUILTINS = {
    "console", "Math", "JSON", "Object", "Array", "String", "Number",
    "Boolean", "Date", "RegExp", "Promise", "Map", "Set", "Error",
    "parseInt", "parseFloat", "isNaN", "isFinite", "require", "exports",
    "module", "process", "undefined", "null", "true", "false", "NaN",
    "Infinity", "this", "arguments", "global", "window", "document",
}

JS_KEYWORDS = {
    "const", "let", "var", "function", "return", "if", "else", "for",
    "while", "do", "switch", "case", "break", "continue", "default",
    "try", "catch", "finally", "throw", "new", "typeof", "instanceof",
    "in", "of", "import", "export", "from", "as", "async", "await",
    "class", "extends", "super", "yield",
}


class JsUndefinedVariableDetector(Detector):
    name = "js_undefined_variable"

    def detect(self, code: str) -> list[Issue]:
        issues: list[Issue] = []
        lines = code.splitlines()

        declared_names: set[str] = set()
        for line in lines:
            # Match function declarations: function foo(param1, param2)
            fn_matches = re.findall(r'function\s*(\w+)?\s*\(([^)]*)\)', line)
            for fn_name, params in fn_matches:
                if fn_name:
                    declared_names.add(fn_name)
                for p in params.split(","):
                    p_clean = p.strip().split("=")[0].strip()
                    if p_clean and re.match(r'^[a-zA-Z_$][a-zA-Z0-9_$]*$', p_clean):
                        declared_names.add(p_clean)

            # Match arrow function params: (a, b) =>
            arrow_matches = re.findall(r'\(([^)]*)\)\s*=>', line)
            for params in arrow_matches:
                for p in params.split(","):
                    p_clean = p.strip().split("=")[0].strip()
                    if p_clean and re.match(r'^[a-zA-Z_$][a-zA-Z0-9_$]*$', p_clean):
                        declared_names.add(p_clean)

            # Match const/let/var declarations: const x = ... / let a, b = ...
            decl_matches = re.findall(r'\b(?:const|let|var)\s+([^=;\n]+)', line)
            for match in decl_matches:
                for var_item in match.split(","):
                    var_clean = var_item.strip().split(":")[0].strip()
                    if var_clean and re.match(r'^[a-zA-Z_$][a-zA-Z0-9_$]*$', var_clean):
                        declared_names.add(var_clean)

        # Find used identifiers
        for line_idx, line in enumerate(lines, start=1):
            clean_line = re.sub(r'(["\']).*?\1', '', line)  # Strip string literals
            clean_line = re.sub(r'//.*$', '', clean_line)     # Strip comments
            words = re.findall(r'\b[a-zA-Z_$][a-zA-Z0-9_$]*\b', clean_line)

            for word in words:
                if word in declared_names or word in JS_BUILTINS or word in JS_KEYWORDS:
                    continue
                # If word is followed by a dot (e.g. obj.prop), it's likely a member access or receiver
                # Search closest match in declared scope
                closest = difflib.get_close_matches(word, list(declared_names), n=1, cutoff=0.6)
                if closest:
                    issues.append(Issue(
                        error_type=ErrorType.UNDEFINED_VARIABLE,
                        line=line_idx,
                        message=f"`{word}` is undefined in JavaScript scope — did you mean `{closest[0]}`?",
                        detail=f"{word}->{closest[0]}",
                        confidence=0.90,
                    ))

        return issues

    def fix(self, code: str, issues: list[Issue]) -> Fix:
        fixed_code = code
        for issue in issues:
            if "->" in issue.detail:
                old_name, new_name = issue.detail.split("->", 1)
                pattern = rf'\b{re.escape(old_name)}\b'
                fixed_code = re.sub(pattern, new_name, fixed_code)

        explanations = [f"`{i.detail.split('->')[0]}` → `{i.detail.split('->')[1]}`" for i in issues if "->" in i.detail]
        explanation = f"Renamed undefined JavaScript identifier typo(s): {', '.join(explanations)}."

        return Fix(
            fixed_code=fixed_code,
            explanation=explanation,
            issues_addressed=issues,
            source="local_engine_js",
        )
