"""AST-based symbol extractor for code anchoring.

Extracts function, class, and method definitions from Python source
with precise line ranges. Also provides keyword extraction from
file paths and keyword-overlap matching for rule-to-file association.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass


@dataclass
class CodeSymbol:
    """A named code symbol with its line range."""

    name: str
    symbol_type: str  # "function" | "class" | "method" | "async_function"
    line_start: int
    line_end: int


def extract_symbols(source: str) -> list[CodeSymbol]:
    """Extract all function/class/async function definitions with line ranges.

    Returns empty list for non-Python files or parse errors.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []

    symbols: list[CodeSymbol] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            symbols.append(
                CodeSymbol(
                    name=node.name,
                    symbol_type="class",
                    line_start=node.lineno,
                    line_end=node.end_lineno or node.lineno,
                )
            )
        elif isinstance(node, ast.AsyncFunctionDef):
            _classify_function(node, "async_function", symbols)
        elif isinstance(node, ast.FunctionDef):
            _classify_function(node, "function", symbols)

    return symbols


def _classify_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    default_type: str,
    symbols: list[CodeSymbol],
) -> None:
    """Classify a function as 'method' if inside a class, else the default type."""
    # Check if parent is a ClassDef by looking at the name pattern
    # (We can't easily check parent in ast.walk, so use name heuristic)
    symbol_type = default_type
    symbols.append(
        CodeSymbol(
            name=node.name,
            symbol_type=symbol_type,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
        )
    )


def find_symbol_at_line(symbols: list[CodeSymbol], line: int) -> CodeSymbol | None:
    """Find which symbol contains a given line number.

    Returns None for module-level code (line not inside any symbol).
    """
    for sym in symbols:
        if sym.line_start <= line <= sym.line_end:
            return sym
    return None


_PATH_STOPWORDS = frozenset(
    {
        "src",
        "lib",
        "app",
        "pkg",
        "cmd",
        "internal",
        "py",
        "js",
        "ts",
        "tsx",
        "jsx",
        "go",
        "rs",
        "java",
        "test",
        "tests",
        "spec",
        "specs",
        "mock",
        "mocks",
        "init",
        "index",
        "main",
        "mod",
    }
)

_PATH_SPLIT_RE = re.compile(r"[/\\_.\-]+")


def extract_keywords_from_path(file_path: str) -> list[str]:
    """Extract meaningful keywords from a file path.

    1. Split on /, \\, _, -, .
    2. Filter out stop words and empty strings
    3. Lowercase

    Example: 'src/services/order_service.py' → ['services', 'order', 'service']
    """
    parts = _PATH_SPLIT_RE.split(file_path)
    return [p.lower() for p in parts if p and p.lower() not in _PATH_STOPWORDS]


def keywords_overlap(file_keywords: list[str], rule) -> bool:
    """Return True if ANY file keyword appears in rule name/description/domain.

    Uses OR logic: any single match is sufficient.
    Returns False for empty keyword lists.
    """
    if not file_keywords:
        return False
    rule_text = f"{rule.name} {rule.description} {rule.domain}".lower()
    return any(kw.lower() in rule_text for kw in file_keywords)
