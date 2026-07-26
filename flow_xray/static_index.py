"""
Static call graph for Python source — the possibility side of flow-xray.

Where ``trace.py`` records what actually happened in one run, this module
answers "what could call this, according to the code" by parsing source with
``ast`` (no execution, no imports of the target project). Ported from
factool's proven query shape (callers / callees / blast-radius / unused)
rather than its FASM parser — the model carries over, the language-specific
extraction doesn't.

Function identity is Python's own ``__qualname__`` convention
(``Class.method``, ``outer.<locals>.inner``), so a :class:`StaticIndex`
node name lines up directly with a ``TraceNode.name`` from the same
codebase without any translation step.

Known limitation, same spirit as factool's FASM caveat: only calls
``ast`` can see syntactically are recorded. Dynamic dispatch, decorators
that swap out the wrapped function, monkey-patching, and callbacks passed
as values are invisible here. Treat results as "statically detected
calls", not ground truth — the merge with runtime trace data is what
makes that distinction visible instead of silently wrong.

Usage::

    from flow_xray.static_index import build_index

    index = build_index(["agent.py"])
    index.callers("Agent.plan")
    index.callees("Agent.plan")
    index.blast_radius("call_database")
    index.unused()
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

_DEFAULT_EXCLUDE_DIRS = {
    ".git", ".hg", ".svn", "__pycache__", ".venv", "venv", ".tox",
    "node_modules", "dist", "build", ".eggs", ".mypy_cache", ".pytest_cache",
}


@dataclass
class FuncDef:
    """A single function/method definition found by the indexer."""

    qualname: str
    name: str
    file: str
    lineno: int
    decorators: list[str] = field(default_factory=list)


class StaticIndex:
    """Static call graph over a set of Python files.

    Mirrors factool's model directly: a table of known functions, a set of
    (caller, callee) edges, and the same four queries. Callee strings are
    recorded even when they don't resolve to a known ``FuncDef`` — e.g.
    ``obj.method()`` where ``obj``'s type isn't known statically — matching
    factool's "record the string, don't require a join" approach.
    """

    def __init__(self) -> None:
        self.functions: dict[str, FuncDef] = {}
        self.calls: set[tuple[str, str]] = set()
        self.files: set[str] = set()
        # (caller_qualname, enclosing-scope chain, bare name) — resolved by
        # resolve() once every file has been added, so forward references and
        # sibling nested functions (visited before their def, in source order)
        # still match.
        self._pending_name_calls: list[tuple[str, tuple[str, ...], str]] = []

    def add_file(self, path: Path, source: str, *, rel_to: Path | None = None) -> None:
        file_label = str(path.relative_to(rel_to)) if rel_to else str(path)
        self.files.add(file_label)
        try:
            tree = ast.parse(source, filename=file_label)
        except SyntaxError:
            return
        _FileVisitor(self, file_label).visit(tree)

    def resolve(self) -> None:
        """Resolve deferred bare-name calls against the full function set.

        Call once after all files are added (``build_index`` does this for
        you). Tries the enclosing-scope chain first — innermost scope
        outward — then falls back to any function of that simple name
        anywhere in the index, then to the bare name itself (recorded
        unresolved, e.g. an imported or builtin call).
        """
        if not self._pending_name_calls:
            return
        by_simple_name: dict[str, list[str]] = {}
        for qualname, fd in self.functions.items():
            by_simple_name.setdefault(fd.name, []).append(qualname)

        for caller, scope_chain, name in self._pending_name_calls:
            callee = self._resolve_name_in_scope(scope_chain, name, by_simple_name)
            self.calls.add((caller, callee))
        self._pending_name_calls.clear()

    def _resolve_name_in_scope(
        self, scope_chain: tuple[str, ...], name: str, by_simple_name: dict[str, list[str]],
    ) -> str:
        parts = list(scope_chain)
        while parts:
            candidate = ".".join([*parts, name])
            if candidate in self.functions:
                return candidate
            parts.pop()
        matches = by_simple_name.get(name)
        if matches:
            return sorted(matches, key=lambda q: (q.count("."), q))[0]
        return name

    def callers(self, name: str) -> list[str]:
        return sorted({c for c, callee in self.calls if callee == name})

    def callees(self, name: str) -> list[str]:
        return sorted({callee for c, callee in self.calls if c == name})

    def blast_radius(self, name: str) -> list[str]:
        """All callers transitively reachable — direct, and callers of callers."""
        seen: set[str] = set()
        frontier = [name]
        while frontier:
            current = frontier.pop()
            for c in self.callers(current):
                if c not in seen:
                    seen.add(c)
                    frontier.append(c)
        seen.discard(name)
        return sorted(seen)

    def unused(self, entry_points: Iterable[str] = ("main", "__main__")) -> list[str]:
        """Known functions never seen as a callee anywhere. Candidates, not a verdict."""
        called = {callee for _, callee in self.calls}
        entry = set(entry_points)
        return sorted(
            qualname for qualname in self.functions
            if qualname not in called and qualname not in entry and self.functions[qualname].name not in entry
        )


class _FileVisitor(ast.NodeVisitor):
    """Walks one module, tracking a Class/Function scope stack to build
    real ``__qualname__``-style names as it goes."""

    def __init__(self, index: StaticIndex, file_label: str) -> None:
        self.index = index
        self.file_label = file_label
        self._scope_parts: list[str] = []
        self._caller_stack: list[str] = ["<module>"]

    def _qualname(self, name: str) -> str:
        return ".".join([*self._scope_parts, name]) if self._scope_parts else name

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._scope_parts.append(node.name)
        self.generic_visit(node)
        self._scope_parts.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualname = self._qualname(node.name)
        decorators = [_decorator_name(d) for d in node.decorator_list]
        self.index.functions[qualname] = FuncDef(
            qualname=qualname,
            name=node.name,
            file=self.file_label,
            lineno=node.lineno,
            decorators=decorators,
        )
        self._scope_parts.append(f"{node.name}.<locals>")
        self._caller_stack.append(qualname)
        self.generic_visit(node)
        self._caller_stack.pop()
        self._scope_parts.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            self.index._pending_name_calls.append(
                (self._caller_stack[-1], tuple(self._scope_parts), node.func.id)
            )
        else:
            callee = self._resolve_callee(node.func)
            if callee is not None:
                self.index.calls.add((self._caller_stack[-1], callee))
        self.generic_visit(node)

    def _resolve_callee(self, func: ast.expr) -> str | None:
        if isinstance(func, ast.Attribute):
            value = func.value
            if isinstance(value, ast.Name) and value.id in ("self", "cls") and len(self._scope_parts) >= 1:
                # Innermost enclosing class, i.e. everything before the first
                # ".<locals>" — best-effort, ignores inheritance.
                class_parts: list[str] = []
                for part in self._scope_parts:
                    if part.endswith(".<locals>"):
                        break
                    class_parts.append(part)
                if class_parts:
                    return f"{'.'.join(class_parts)}.{func.attr}"
            return func.attr
        return None


def _decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _decorator_name(node.func)
    return "?"


def build_index(
    paths: Iterable[str | Path],
    *,
    exclude_dirs: Iterable[str] = _DEFAULT_EXCLUDE_DIRS,
) -> StaticIndex:
    """Build a :class:`StaticIndex` from files and/or directories.

    Directories are walked recursively for ``*.py`` files, skipping common
    non-project dirs (``.venv``, ``__pycache__``, ``node_modules``, …).
    Paths are recorded relative to the shortest common directory-argument
    ancestor when possible, else as given.
    """
    exclude = set(exclude_dirs)
    index = StaticIndex()
    roots = [Path(p).resolve() for p in paths]
    for root in roots:
        rel_to = root if root.is_dir() else root.parent
        if root.is_dir():
            for py_file in sorted(root.rglob("*.py")):
                if any(part in exclude for part in py_file.parts):
                    continue
                _index_one(index, py_file, rel_to)
        elif root.is_file():
            _index_one(index, root, rel_to)
    index.resolve()
    return index


def _index_one(index: StaticIndex, py_file: Path, rel_to: Path) -> None:
    try:
        source = py_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return
    index.add_file(py_file, source, rel_to=rel_to)
