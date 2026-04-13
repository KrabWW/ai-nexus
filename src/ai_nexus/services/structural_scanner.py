"""Structural code scanner — multi-language pattern matching.

Wraps ast-grep CLI (`sg`) for multi-language structural search with
automatic fallback to Python's stdlib `ast` module for Python files.

Usage:
    scanner = StructuralScanner()

    # Symbol extraction (find functions/classes)
    symbols = await scanner.extract_symbols("src/order.py")

    # Pattern matching (ast-grep patterns like "$FUNC($$$ARGS)")
    matches = await scanner.scan_patterns("src/order.py", patterns=["console.log($MSG)"])

    # Batch scan multiple files
    results = await scanner.scan_files(["src/a.py", "src/b.ts"])
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from dataclasses import dataclass, field

from ai_nexus.services.ast_analyzer import (
    CodeSymbol,
    extract_keywords_from_path,
)
from ai_nexus.services.ast_analyzer import (
    extract_symbols as py_extract_symbols,
)

logger = logging.getLogger(__name__)

# File extension → ast-grep language name
_LANG_MAP: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".swift": "swift",
    ".c": "c",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".html": "html",
    ".css": "css",
}


def _detect_language(file_path: str) -> str | None:
    """Detect language from file extension."""
    _, ext = os.path.splitext(file_path)
    return _LANG_MAP.get(ext)


def _is_sg_available() -> bool:
    """Check if ast-grep CLI (`sg`) is on PATH."""
    return shutil.which("sg") is not None


@dataclass
class PatternMatch:
    """A single pattern match from structural scanning."""

    file_path: str
    language: str
    pattern: str
    line_start: int
    line_end: int
    text: str
    matched_node: str = ""  # The captured variable if any


@dataclass
class FileScanResult:
    """Structural scan results for a single file."""

    file_path: str
    language: str | None
    symbols: list[CodeSymbol] = field(default_factory=list)
    pattern_matches: list[PatternMatch] = field(default_factory=list)
    error: str | None = None


class StructuralScanner:
    """Multi-language structural code scanner.

    Uses ast-grep CLI when available, falls back to Python ast module.
    """

    def __init__(self) -> None:
        self._sg_available = _is_sg_available()

    async def extract_symbols(self, file_path: str) -> FileScanResult:
        """Extract symbols (functions, classes) from a source file."""
        lang = _detect_language(file_path)

        if lang == "python":
            return await self._extract_python_symbols(file_path)

        if self._sg_available and lang:
            return await self._extract_via_sg(file_path, lang)

        return FileScanResult(
            file_path=file_path,
            language=lang,
            symbols=await self._keyword_fallback(file_path),
        )

    async def scan_patterns(
        self,
        file_path: str,
        patterns: list[str],
        language: str | None = None,
    ) -> FileScanResult:
        """Scan a file for structural patterns (ast-grep syntax).

        Patterns use ast-grep metavariable syntax:
          $NAME  — match any single AST node
          $$$ARGS — match multiple nodes
        """
        lang = language or _detect_language(file_path)

        if not self._sg_available or not lang:
            return FileScanResult(
                file_path=file_path,
                language=lang,
                pattern_matches=[],
            )

        matches: list[PatternMatch] = []
        for pattern in patterns:
            try:
                hits = await self._run_sg_search(file_path, lang, pattern)
                matches.extend(hits)
            except Exception as e:
                logger.warning("ast-grep pattern '%s' failed: %s", pattern, e)

        return FileScanResult(
            file_path=file_path,
            language=lang,
            pattern_matches=matches,
        )

    async def scan_files(
        self,
        file_paths: list[str],
        patterns: list[str] | None = None,
    ) -> list[FileScanResult]:
        """Batch scan multiple files for symbols and optional patterns."""
        results: list[FileScanResult] = []
        for fp in file_paths:
            if not os.path.isfile(fp):
                results.append(FileScanResult(
                    file_path=fp,
                    language=_detect_language(fp),
                    error="File not found",
                ))
                continue

            result = await self.extract_symbols(fp)
            if patterns:
                lang = result.language
                if self._sg_available and lang:
                    for pattern in patterns:
                        try:
                            hits = await self._run_sg_search(fp, lang, pattern)
                            result.pattern_matches.extend(hits)
                        except Exception as e:
                            logger.warning("ast-grep scan failed for %s: %s", fp, e)
            results.append(result)

        return results

    # ── Private ──────────────────────────────────────────────────

    async def _extract_python_symbols(self, file_path: str) -> FileScanResult:
        """Use Python stdlib ast module for symbol extraction."""
        try:
            with open(file_path) as f:
                source = f.read()
            symbols = py_extract_symbols(source)
            return FileScanResult(
                file_path=file_path,
                language="python",
                symbols=symbols,
            )
        except Exception as e:
            return FileScanResult(
                file_path=file_path,
                language="python",
                error=str(e),
            )

    async def _extract_via_sg(self, file_path: str, language: str) -> FileScanResult:
        """Use ast-grep CLI to extract class/function definitions."""
        # Use ast-grep patterns to find functions and classes
        func_pattern = "def $NAME($$$ARGS)" if language == "python" else "function $NAME($$$ARGS)"
        class_pattern = "class $NAME $$$BODY"

        symbols: list[CodeSymbol] = []
        for pattern in [func_pattern, class_pattern]:
            try:
                hits = await self._run_sg_search(file_path, language, pattern)
                for hit in hits:
                    sym_type = "class" if "class" in pattern else "function"
                    symbols.append(CodeSymbol(
                        name=hit.matched_node or hit.text.split("(")[0].strip(),
                        symbol_type=sym_type,
                        line_start=hit.line_start,
                        line_end=hit.line_end,
                    ))
            except Exception as e:
                logger.warning("sg extract failed: %s", e)

        return FileScanResult(file_path=file_path, language=language, symbols=symbols)

    async def _keyword_fallback(self, file_path: str) -> list[CodeSymbol]:
        """When no structural analysis is available, return keyword-based pseudo-symbols."""
        kws = extract_keywords_from_path(file_path)
        if not kws:
            return []
        return [CodeSymbol(name=kw, symbol_type="keyword", line_start=0, line_end=0) for kw in kws]

    async def _run_sg_search(
        self, file_path: str, language: str, pattern: str,
    ) -> list[PatternMatch]:
        """Run ast-grep CLI search and parse JSON output."""
        cmd = [
            "sg", "run",
            "--pattern", pattern,
            "--language", language,
            "--json", "compact",
            file_path,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode().strip()
            if "no matches" in error_msg.lower() or proc.returncode == 0:
                return []
            raise RuntimeError(f"sg exited {proc.returncode}: {error_msg}")

        return self._parse_sg_output(stdout.decode(), file_path, language, pattern)

    @staticmethod
    def _parse_sg_output(
        output: str, file_path: str, language: str, pattern: str,
    ) -> list[PatternMatch]:
        """Parse ast-grep compact JSON output into PatternMatch objects."""
        import json

        if not output.strip():
            return []

        matches: list[PatternMatch] = []
        try:
            # ast-grep compact JSON: one JSON object per line
            for line in output.strip().splitlines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                # ast-grep compact format: [{"range": {"byteOffset": ...}, "text": "..."}]
                # or the standard match format with "matches" array
                items = obj if isinstance(obj, list) else obj.get("matches", [])
                for item in items:
                    range_info = item.get("range", {})
                    # ast-grep uses different range formats depending on version
                    start = range_info.get("start", {})
                    end = range_info.get("end", {})
                    line_start = start.get("line", 0)
                    line_end = end.get("line", line_start)
                    text = item.get("text", "")
                    # Extract metavariable captures
                    captures = item.get("captures", {})
                    matched_node = ""
                    for _var_name, var_val in captures.items():
                        if isinstance(var_val, dict):
                            matched_node = var_val.get("text", str(var_val))
                        else:
                            matched_node = str(var_val)
                        break

                    matches.append(PatternMatch(
                        file_path=file_path,
                        language=language,
                        pattern=pattern,
                        line_start=line_start,
                        line_end=line_end,
                        text=text,
                        matched_node=matched_node,
                    ))
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to parse sg output: %s", e)

        return matches
