from __future__ import annotations

import ast
import builtins
import difflib
import re

from core.detectors.base import Detector
from core.detectors.missing_import import KNOWN_MODULES
from core.models import ErrorType, Fix, Issue

BUILTIN_NAMES = set(dir(builtins))
_MATCH_CUTOFF = 0.72  # how close a name must be to count as "probably a typo"


class _ScopeCollector(ast.NodeVisitor):
    """Same idea as the import collector, but we keep *all* defined names
    (locals, params, imports, functions, classes) as the candidate pool
    that a misspelled name is probably a typo of.
    """

    def __init__(self) -> None:
        self.used: dict[str, int] = {}
        self.defined: set[str] = set()

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.used.setdefault(node.id, node.lineno)
        else:
            self.defined.add(node.id)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.defined.add((alias.asname or alias.name).split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self.defined.add(alias.asname or alias.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.defined.add(node.name)
        for arg in node.args.args + node.args.kwonlyargs:
            self.defined.add(arg.arg)
        if node.args.vararg:
            self.defined.add(node.args.vararg.arg)
        if node.args.kwarg:
            self.defined.add(node.args.kwarg.arg)
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.defined.add(node.name)
        self.generic_visit(node)


class UndefinedVariableDetector(Detector):
    name = "undefined_variable"

    def detect(self, code: str) -> list[Issue]:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []  # the syntax detector owns this case

        collector = _ScopeCollector()
        collector.visit(tree)

        issues: list[Issue] = []
        for used_name, lineno in collector.used.items():
            if used_name in collector.defined or used_name in BUILTIN_NAMES:
                continue
            if used_name in KNOWN_MODULES:
                continue  # the missing-import detector owns this one

            candidates = difflib.get_close_matches(
                used_name, collector.defined, n=1, cutoff=_MATCH_CUTOFF
            )
            if candidates:
                issues.append(
                    Issue(
                        error_type=ErrorType.UNDEFINED_VARIABLE,
                        line=lineno,
                        message=f"`{used_name}` is never defined — did you mean `{candidates[0]}`?",
                        detail=candidates[0],
                        confidence=0.85,
                    )
                )
        return issues

    def fix(self, code: str, issues: list[Issue]) -> Fix:
        fixed_code = code
        renamed: list[str] = []
        for issue in issues:
            wrong = issue.message.split("`")[1]
            correct = issue.detail
            pattern = rf"\b{re.escape(wrong)}\b"
            new_code, n = re.subn(pattern, correct, fixed_code)
            if n:
                fixed_code = new_code
                renamed.append(f"`{wrong}` → `{correct}`")

        explanation = (
            "These names never appear on the left-hand side of an assignment or in a "
            "function signature anywhere above — Python would raise a `NameError` the "
            "moment that line runs. Closest matching name(s) already in scope: "
            + ", ".join(renamed) + "."
        ) if renamed else "Found a possibly undefined name, but no confident rename was available."
        return Fix(fixed_code=fixed_code, explanation=explanation, issues_addressed=issues, source="local_engine")
