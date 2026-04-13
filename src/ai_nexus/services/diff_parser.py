"""Unified diff parser for code anchoring.

Parses git unified diff output into structured FileDiff/Hunk objects
with file paths and line ranges. Handles binary files, renames,
deletions, and mode changes gracefully.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_DIFF_HEADER_RE = re.compile(r"^diff --git a/.+ b/(.+)$")


@dataclass
class DiffHunk:
    """A single hunk from a unified diff."""

    file_path: str
    line_start: int  # target-side line number where hunk starts
    line_end: int  # target-side line number where hunk ends
    content: str  # the changed lines (with +/- prefixes)


@dataclass
class FileDiff:
    """All hunks for a single file in a diff."""

    file_path: str  # new path (handles renames)
    hunks: list[DiffHunk] = field(default_factory=list)


def parse_unified_diff(diff_text: str) -> list[FileDiff]:
    """Parse unified diff into file diffs with hunks.

    Skips binary files, mode changes, deleted files, and non-UTF8 content.
    """
    if not diff_text or not diff_text.strip():
        return []

    results: list[FileDiff] = []
    current_file: FileDiff | None = None
    current_hunk_lines: list[str] = []
    hunk_start: int = 0
    hunk_end: int = 0
    in_hunk = False
    skip_file = False

    for line in diff_text.splitlines():
        # New file header
        m = _DIFF_HEADER_RE.match(line)
        if m:
            # Finalize previous hunk/file
            _finalize_hunk(
                current_file, current_hunk_lines, hunk_start, hunk_end, in_hunk,
            )
            # Add previous file to results if it has hunks
            if current_file is not None and current_file.hunks:
                results.append(current_file)

            in_hunk = False
            current_hunk_lines = []

            current_file = FileDiff(file_path=m.group(1))
            skip_file = False
            continue

        if current_file is None or skip_file:
            continue

        # Skip binary files
        if line.startswith("Binary files") or line.startswith("GIT binary patch"):
            skip_file = True
            continue

        # Check for deleted file
        if line.startswith("+++ /dev/null"):
            skip_file = True
            current_file = None
            continue

        # Skip mode changes and other metadata
        skip_prefixes = (
            "old mode ",
            "new mode ",
            "similarity index",
            "rename from",
            "copy from",
        )
        if line.startswith(skip_prefixes):
            continue

        # Hunk header
        hm = _HUNK_RE.match(line)
        if hm:
            # Finalize previous hunk
            _finalize_hunk(
                current_file, current_hunk_lines, hunk_start, hunk_end, in_hunk,
            )
            current_hunk_lines = []

            new_start = int(hm.group(3))
            new_count = int(hm.group(4)) if hm.group(4) is not None else 1
            hunk_start = new_start
            hunk_end = new_start + new_count - 1 if new_count > 0 else new_start
            in_hunk = True
            continue

        # Content lines within a hunk
        if in_hunk and (line.startswith(("+", "-", " ")) or line == "\\ No newline at end of file"):
            current_hunk_lines.append(line)
            continue

    # Finalize last hunk/file
    _finalize_hunk(current_file, current_hunk_lines, hunk_start, hunk_end, in_hunk)
    if current_file is not None and current_file.hunks:
        results.append(current_file)

    return results


def _finalize_hunk(
    file: FileDiff | None,
    lines: list[str],
    start: int,
    end: int,
    in_hunk: bool,
) -> None:
    """Add the current hunk to the file if active."""
    if file is not None and in_hunk and lines:
        file.hunks.append(
            DiffHunk(
                file_path=file.file_path,
                line_start=start,
                line_end=end,
                content="\n".join(lines),
            )
        )


def extract_snippet(hunk_content: str, context: int = 3) -> str:
    """Extract code snippet from hunk content, stripping +/- prefixes.

    Returns up to `context` changed lines with their surrounding context lines.
    """
    if not hunk_content:
        return ""

    lines: list[str] = []
    for line in hunk_content.splitlines():
        if line.startswith("\\"):
            continue
        # Strip the +/-/space prefix
        if line and line[0] in ("+", "-", " "):
            lines.append(line[1:])
        else:
            lines.append(line)

    # Limit to context lines
    if len(lines) > context * 2 + 5:
        # Keep first context lines, indicator, and last context lines
        half = context + 2
        lines = lines[:half] + ["..."] + lines[-half:]

    return "\n".join(lines)
