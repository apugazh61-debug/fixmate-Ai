from __future__ import annotations

import ast
import builtins

from core.detectors.base import Detector
from core.models import ErrorType, Fix, Issue

# Common short names -> the import statement that defines them.
# This is the "knowledge base" the local engine uses instead of an LLM.
KNOWN_MODULES: dict[str, str] = {
    "os": "import os",
    "sys": "import sys",
    "math": "import math",
    "random": "import random",
    "json": "import json",
    "re": "import re",
    "time": "import time",
    "datetime": "import datetime",
    "itertools": "import itertools",
    "collections": "import collections",
    "functools": "import functools",
    "pathlib": "import pathlib",
    "subprocess": "import subprocess",
    "logging": "import logging",
    "np": "import numpy as np",
    "pd": "import pandas as pd",
    "requests": "import requests",
    "plt": "import matplotlib.pyplot as plt",
}

BUILTIN_NAMES = set(dir(builtins))


class _NameUsageCollector(ast.NodeVisitor):
    """Walks the AST once, recording every name that is *used* (Load
    context) and every name that is *defined* somewhere (import, assignment,
    function/class def, parameter, comprehension target, etc.).
    """

    def __init__(self) -> None:
        self.used: dict[str, int] = {}   # name -> first line seen
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

    def visit_arg(self, node: ast.arg) -> None:
        self.defined.add(node.arg)


class MissingImportDetector(Detector):
    name = "missing_import"

    def detect(self, code: str) -> list[Issue]:
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []  # the syntax detector owns this case

        collector = _NameUsageCollector()
        collector.visit(tree)

        issues: list[Issue] = []
        for used_name, lineno in collector.used.items():
            if used_name in collector.defined or used_name in BUILTIN_NAMES:
                continue
            if used_name in KNOWN_MODULES:
                issues.append(
                    Issue(
                        error_type=ErrorType.MISSING_IMPORT,
                        line=lineno,
                        message=f"`{used_name}` is used but never imported.",
                        detail=KNOWN_MODULES[used_name],
                        confidence=0.95,
                    )
                )
        return issues

    def fix(self, code: str, issues: list[Issue]) -> Fix:
        import_lines = sorted({issue.detail for issue in issues})
        lines = code.splitlines()

        insert_at = 0
        if lines and lines[0].startswith("#!"):
            insert_at = 1
        if len(lines) > insert_at and lines[insert_at].lstrip().startswith(('"""', "'''")):
            quote = lines[insert_at].lstrip()[:3]
            insert_at += 1
            while insert_at < len(lines) and quote not in lines[insert_at]:
                insert_at += 1
            insert_at += 1

        new_lines = lines[:insert_at] + import_lines + lines[insert_at:]
        # Only pad with a blank separator line if the next line isn't already
        # blank or another import — keeps repeated fix passes from stacking
        # up empty lines between import blocks.
        next_line = lines[insert_at] if insert_at < len(lines) else ""
        if import_lines and next_line.strip() and not next_line.lstrip().startswith(("import ", "from ")):
            new_lines = lines[:insert_at] + import_lines + [""] + lines[insert_at:]
        fixed_code = "\n".join(new_lines)

        names = ", ".join(sorted({i.message.split("`")[1] for i in issues}))
        explanation = (
            f"`{names}` was used but no `import` statement for it existed anywhere "
            f"above, so Python would raise a `NameError` the moment that line runs. "
            f"Added the missing import(s) at the top of the file: "
            f"{'; '.join(import_lines)}."
        )
        return Fix(fixed_code=fixed_code, explanation=explanation, issues_addressed=issues, source="local_engine")
