"""Stress-tests beyond the 4 happy-path examples: tricky-but-valid Python
that must NOT be touched (false-positive check), plus harder bug shapes."""
import ast
import sys

from core.engine import run_local_pipeline

CASES = [
    ("decorator + nested fn (must stay untouched, no false positive)", '''
import functools

def cache(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)
    return wrapper

@cache
def add(a, b):
    return a + b
''', True, True),  # (label, code, expect_verified, expect_no_issues)

    ("walrus operator + comprehension (must stay untouched)", '''
data = [1, 2, 3, 4, 5]
result = [y for x in data if (y := x * 2) > 4]
print(result)
''', True, True),

    ("lambda + multiple assignment (must stay untouched)", '''
a, b = 1, 2
square = lambda x: x * x
print(square(a), square(b))
''', True, True),

    ("class with method using self (must stay untouched)", '''
class Counter:
    def __init__(self):
        self.count = 0

    def increment(self):
        self.count += 1
        return self.count
''', True, True),

    ("global / nonlocal (must stay untouched)", '''
counter = 0

def bump():
    global counter
    counter += 1

def outer():
    x = 0
    def inner():
        nonlocal x
        x += 1
    inner()
    return x
''', True, True),

    ("f-string with braces (must stay untouched)", '''
name = "world"
greeting = f"hello, {name}!"
print(greeting)
''', True, True),

    ("missing closing parenthesis (harder syntax repair)", '''
def total(a, b):
    return (a + b

print(total(1, 2))
''', None, None),  # just must not crash; verified may or may not be True

    ("empty input", "", True, True),

    ("comment-only input", "# just a comment\n", True, True),

    ("multiple undefined typos in one function", '''
def process(records):
    cleaned = []
    for rec in record:
        cleaned.append(rec.strip())
    return cleand
''', True, None),
]


def main() -> int:
    failures = 0
    for label, code, expect_verified, expect_no_issues in CASES:
        print(f"\n{'='*70}\n{label}\n{'='*70}")
        try:
            result = run_local_pipeline(code)
        except Exception as exc:  # the real test: must never crash
            print(f"  !! CRASHED: {type(exc).__name__}: {exc}")
            failures += 1
            continue

        parses = True
        try:
            ast.parse(result.fixed_code)
        except SyntaxError:
            parses = False

        print(f"  verified={result.verified}  issues={len(result.issues)}  parses_ok={parses}")
        if result.issues:
            for i in result.issues:
                print(f"    - {i.error_type.value} @ line {i.line}: {i.message}")

        if expect_verified is not None and result.verified != expect_verified:
            print(f"  !! expected verified={expect_verified}, got {result.verified}")
            failures += 1
        if expect_no_issues is True and result.issues:
            print(f"  !! expected NO issues (false positive risk), got {len(result.issues)}")
            failures += 1
        if expect_no_issues is True and result.fixed_code.strip() != code.strip():
            print("  !! code was modified when it should have been left untouched")
            print("  --- resulting diff ---")
            print(result.fixed_code)
            failures += 1

    print(f"\n{'='*70}\n{len(CASES)-failures}/{len(CASES)} stress cases OK\n{'='*70}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
