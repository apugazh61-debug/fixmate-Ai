"""
Verification script for FixMate AI workspace integrity.
Runs py_compile on all .py files and checks for bare except clauses.
"""

import ast
import os
import py_compile
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent

def check_py_compile():
    print("--- 1. Running py_compile on all workspace Python files ---")
    py_files = [f for f in REPO_ROOT.rglob("*.py") if "__pycache__" not in str(f) and ".git" not in str(f)]
    for f in py_files:
        try:
            py_compile.compile(str(f), doraise=True)
            print(f"  [OK] {f.relative_to(REPO_ROOT)}")
        except py_compile.PyCompileError as exc:
            print(f"  [FAIL] {f.relative_to(REPO_ROOT)}: {exc}")
            return False
    print(f"\nTotal {len(py_files)} Python files compiled cleanly with 0 errors.\n")
    return True


def check_bare_excepts():
    print("--- 2. Checking for bare except: or swallowed exceptions in test suite ---")
    test_files = [f for f in REPO_ROOT.glob("test_*.py")]
    bare_except_found = 0
    for f in test_files:
        content = f.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    print(f"  [WARNING] Bare except found in {f.name} at line {node.lineno}")
                    bare_except_found += 1
                elif isinstance(node.type, ast.Name) and node.type.id == "Exception":
                    # Check if body is just 'pass'
                    if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                        print(f"  [WARNING] 'except Exception: pass' found in {f.name} at line {node.lineno}")
                        bare_except_found += 1
    if bare_except_found == 0:
        print("  [OK] Zero bare excepts or 'except Exception: pass' found in test suites.")
    return bare_except_found == 0


if __name__ == "__main__":
    ok1 = check_py_compile()
    ok2 = check_bare_excepts()
    sys.exit(0 if ok1 and ok2 else 1)
