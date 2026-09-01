"""
Tests for core/context_gatherer.py.

Verifies:
1. Static resolution of relative and package imports across sibling files in a package.
2. Enforcing max file and max line budget constraints.
3. Graceful degradation on standalone files and non-existent paths.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from core import context_gatherer


def test_package_import_resolution():
    print("\n--- Test: Multi-file package import resolution ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        pkg_dir = root / "mypackage"
        pkg_dir.mkdir()

        # Create sibling files
        (pkg_dir / "__init__.py").write_text("# init\n", encoding="utf-8")
        (pkg_dir / "models.py").write_text("class User:\n    name: str = 'Alice'\n", encoding="utf-8")
        (pkg_dir / "utils.py").write_text("def format_name(user):\n    return user.name.upper()\n", encoding="utf-8")
        
        main_code = """
from .models import User
from .utils import format_name

def get_formatted_user():
    return format_name(User())
"""
        (pkg_dir / "main.py").write_text(main_code, encoding="utf-8")

        ctx = context_gatherer.gather_context(
            repo_root=root,
            file_path="mypackage/main.py",
            code=main_code,
        )

        assert ctx.has_context is True
        assert len(ctx.files) == 2
        file_names = {f.rel_path for f in ctx.files}
        assert "mypackage/models.py" in file_names or "mypackage\\models.py" in file_names
        assert "mypackage/utils.py" in file_names or "mypackage\\utils.py" in file_names
        assert "class User" in ctx.bundled_text
        assert "def format_name" in ctx.bundled_text
        print(f"  Successfully gathered {len(ctx.files)} sibling files.")

    print("  PASS")


def test_budget_and_file_caps():
    print("\n--- Test: Budget and max files cap ---")
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        pkg_dir = root / "largepkg"
        pkg_dir.mkdir()

        # Create 8 sibling files with 50 lines each
        main_imports = []
        for i in range(8):
            fname = f"mod_{i}.py"
            (pkg_dir / fname).write_text(f"# module {i}\n" + "x = 1\n" * 50, encoding="utf-8")
            main_imports.append(f"from . import mod_{i}")

        main_code = "\n".join(main_imports) + "\ndef run(): pass\n"
        (pkg_dir / "main.py").write_text(main_code, encoding="utf-8")

        # Test max 3 files
        ctx_3 = context_gatherer.gather_context(
            repo_root=root,
            file_path="largepkg/main.py",
            code=main_code,
            max_files=3,
        )
        assert len(ctx_3.files) <= 3
        print(f"  Max files cap enforced: {len(ctx_3.files)} <= 3")

        # Test max 60 lines
        ctx_lines = context_gatherer.gather_context(
            repo_root=root,
            file_path="largepkg/main.py",
            code=main_code,
            max_lines=60,
        )
        assert ctx_lines.total_lines <= 60
        print(f"  Max lines cap enforced: {ctx_lines.total_lines} <= 60 lines")

    print("  PASS")


def test_standalone_and_graceful_degradation():
    print("\n--- Test: Standalone script & missing paths ---")
    # 1. Standalone code with no repo_root
    ctx_none = context_gatherer.gather_context(repo_root=None, file_path=None, code="import math\nx = 1")
    assert ctx_none.has_context is False
    assert ctx_none.files == []
    print("  Handled None repo/path gracefully.")

    # 2. Standalone script in empty temp dir
    with tempfile.TemporaryDirectory() as tmpdir:
        script = Path(tmpdir) / "standalone.py"
        script.write_text("import math\nimport sys\n", encoding="utf-8")
        ctx_standalone = context_gatherer.gather_context(
            repo_root=tmpdir,
            file_path="standalone.py",
        )
        assert ctx_standalone.has_context is False
        assert ctx_standalone.files == []
        print("  Handled standalone script with standard library imports only.")

    print("  PASS")


def main() -> int:
    try:
        test_package_import_resolution()
        test_budget_and_file_caps()
        test_standalone_and_graceful_degradation()
        print("\n" + "=" * 60)
        print("ALL CONTEXT GATHERER TESTS PASSED")
        print("=" * 60)
        return 0
    except Exception as exc:
        print(f"\n!! CONTEXT GATHERER TEST FAILED: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
