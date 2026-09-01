"""Quick smoke test for the local (offline) pipeline — no pytest needed."""
import ast
import sys

from core.engine import run_local_pipeline
from examples import EXAMPLES


def main() -> int:
    failures = 0
    for name, code in EXAMPLES.items():
        print(f"\n{'='*70}\n{name}\n{'='*70}")
        result = run_local_pipeline(code)
        print(f"verified={result.verified}  attempts={result.attempts}  issues={len(result.issues)}")
        print("--- trace ---")
        for step in result.trace:
            print(f"  [{step.status:>4}] {step.name}: {step.detail}")
        print("--- explanation ---")
        print(" ", result.explanation)
        print("--- fixed code ---")
        print(result.fixed_code)

        try:
            ast.parse(result.fixed_code)
            parses = True
        except SyntaxError as e:
            parses = False
            print("  !! fixed code still fails to parse:", e)

        if not parses:
            failures += 1

    print(f"\n{'='*70}\n{len(EXAMPLES) - failures}/{len(EXAMPLES)} examples produced parseable fixed code\n{'='*70}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
