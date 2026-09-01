"""
Static AST-based multi-file import graph context gatherer.

Discovers local relative and package imports from a target Python file,
resolves sibling files within the repository, and bundles relevant context
capped to 5 files and ~200 lines max to enrich LLM prompts without token bloat.
"""

from __future__ import annotations

import ast
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path


MAX_RELATED_FILES = 5
MAX_CONTEXT_LINES = 200


@dataclass
class RelatedFileContext:
    """Context snippet from a single related sibling file."""
    rel_path: str
    content: str
    line_count: int


@dataclass
class GatheredContext:
    """Collection of gathered sibling file contexts and combined text."""
    target_file: str
    files: list[RelatedFileContext] = field(default_factory=list)
    total_lines: int = 0
    bundled_text: str = ""

    @property
    def has_context(self) -> bool:
        return bool(self.files)


class _ImportExtractor(ast.NodeVisitor):
    """Extracts local relative and package import targets from an AST."""

    def __init__(self) -> None:
        # tuples of (module_str, level, list_of_imported_names)
        self.imports: list[tuple[str | None, int, list[str]]] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append((alias.name, 0, []))

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        names = [alias.name for alias in node.names]
        self.imports.append((node.module, node.level, names))


def _resolve_import_path(
    current_file: Path,
    repo_root: Path,
    module: str | None,
    level: int,
    names: list[str],
) -> list[Path]:
    """Resolve AST import coordinates to candidate Python files on disk."""
    candidates: list[Path] = []
    current_dir = current_file.parent if current_file.is_file() else current_file

    if level > 0:
        # Relative import: level 1 = current_dir, level 2 = current_dir.parent, etc.
        base = current_dir
        for _ in range(level - 1):
            base = base.parent

        if module:
            mod_path = module.replace(".", "/")
            candidates.append(base / f"{mod_path}.py")
            candidates.append(base / mod_path / "__init__.py")
        else:
            # e.g. from . import foo, bar
            for name in names:
                candidates.append(base / f"{name}.py")
                candidates.append(base / name / "__init__.py")
    else:
        # Absolute / package import (level == 0)
        if module:
            mod_path = module.replace(".", "/")
            # Try from repo_root
            candidates.append(repo_root / f"{mod_path}.py")
            candidates.append(repo_root / mod_path / "__init__.py")
            # Also try from current_dir
            candidates.append(current_dir / f"{mod_path}.py")
            candidates.append(current_dir / mod_path / "__init__.py")

    valid: list[Path] = []
    for cand in candidates:
        try:
            resolved = cand.resolve()
            if resolved.is_file() and resolved != current_file.resolve():
                valid.append(resolved)
        except Exception:  # noqa: BLE001
            continue
    return valid


def gather_context(
    repo_root: str | Path | None,
    file_path: str | Path | None,
    code: str | None = None,
    max_files: int = MAX_RELATED_FILES,
    max_lines: int = MAX_CONTEXT_LINES,
) -> GatheredContext:
    """Extract and bundle sibling context files for the given target file.
    
    Degrades cleanly to empty GatheredContext on any resolution error or
    standalone scripts.
    """
    if not repo_root or not file_path:
        return GatheredContext(target_file=str(file_path or ""))

    try:
        root_path = Path(repo_root).resolve()
        target_path = (root_path / file_path).resolve() if not Path(file_path).is_absolute() else Path(file_path).resolve()
    except Exception:  # noqa: BLE001
        return GatheredContext(target_file=str(file_path))

    target_code = code
    if target_code is None and target_path.is_file():
        try:
            target_code = target_path.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            target_code = None

    if not target_code:
        return GatheredContext(target_file=str(file_path))

    # Parse target AST to find initial imports
    try:
        tree = ast.parse(target_code)
    except SyntaxError:
        return GatheredContext(target_file=str(file_path))

    queue: deque[Path] = deque()
    visited: set[Path] = {target_path}

    extractor = _ImportExtractor()
    extractor.visit(tree)

    for mod, level, names in extractor.imports:
        for found in _resolve_import_path(target_path, root_path, mod, level, names):
            if found not in visited:
                visited.add(found)
                queue.append(found)

    collected_files: list[RelatedFileContext] = []
    total_lines = 0

    while queue and len(collected_files) < max_files and total_lines < max_lines:
        next_file = queue.popleft()
        try:
            content = next_file.read_text(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue

        file_lines = content.splitlines()
        remaining_budget = max_lines - total_lines
        if remaining_budget <= 0:
            break

        if len(file_lines) > remaining_budget:
            truncated_content = "\n".join(file_lines[:remaining_budget]) + "\n# ... [truncated for context limit]"
            snippet_line_count = remaining_budget
        else:
            truncated_content = content
            snippet_line_count = len(file_lines)

        try:
            rel = next_file.relative_to(root_path).as_posix()
        except ValueError:
            rel = next_file.name

        collected_files.append(RelatedFileContext(
            rel_path=rel,
            content=truncated_content,
            line_count=snippet_line_count,
        ))
        total_lines += snippet_line_count

        # Also inspect this sibling's imports if we still have file slots
        if len(collected_files) < max_files and total_lines < max_lines:
            try:
                sib_tree = ast.parse(content)
                sib_extractor = _ImportExtractor()
                sib_extractor.visit(sib_tree)
                for mod, level, names in sib_extractor.imports:
                    for found in _resolve_import_path(next_file, root_path, mod, level, names):
                        if found not in visited:
                            visited.add(found)
                            queue.append(found)
            except SyntaxError:
                pass

    # Build bundled context string
    bundled_parts: list[str] = []
    for ctx in collected_files:
        bundled_parts.append(
            f"--- SIBLING FILE: `{ctx.rel_path}` ({ctx.line_count} lines) ---\n"
            f"{ctx.content}\n"
        )

    bundled_text = "\n".join(bundled_parts)
    return GatheredContext(
        target_file=str(file_path),
        files=collected_files,
        total_lines=total_lines,
        bundled_text=bundled_text,
    )
