"""
gdep.source_reader
Reads actual .cs files and processes them for LLM consumption.
Automatically detects partial classes and collects all related files.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SourceChunk:
    class_name: str
    file_path:  str
    is_partial: bool
    part_index: int       # File index in a partial class sequence
    total_parts: int      # Total number of partial files
    content: str          # Actual code content
    line_count: int


@dataclass
class SourceResult:
    class_name:   str
    is_partial:   bool
    total_parts:  int
    chunks:       list[SourceChunk]
    total_lines:  int
    truncated:    bool    # Whether the content was truncated due to length


# Partial class detection pattern
_PARTIAL_PAT = re.compile(
    r'\bpartial\s+(?:class|struct|interface)\s+(\w+)', re.MULTILINE
)
_CLASS_PAT = re.compile(
    r'(?:public|internal|private|protected)?\s*'
    r'(?:partial\s+)?(?:abstract\s+|sealed\s+|static\s+)?'
    r'(?:class|struct|interface)\s+(\w+)',
    re.MULTILINE
)


def find_class_files(scripts_path: str, class_name: str) -> SourceResult:
    """
    Finds .cs files for the given class name and returns the source code.
    Collects all related files if it's a partial class.
    """
    root = Path(scripts_path)
    if not root.exists():
        return SourceResult(class_name=class_name, is_partial=False,
                            total_parts=0, chunks=[], total_lines=0, truncated=False)

    # 1. Scan all files containing the class declaration
    candidate_files: list[tuple[Path, bool]] = []  # (file_path, is_partial)

    for cs_file in root.rglob("*.cs"):
        if "_PROTO" in cs_file.name:
            continue
        try:
            text = cs_file.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # Find class declaration
        for m in _CLASS_PAT.finditer(text):
            if m.group(1) == class_name:
                is_partial = bool(_PARTIAL_PAT.search(text))
                candidate_files.append((cs_file, is_partial))
                break

    if not candidate_files:
        return SourceResult(class_name=class_name, is_partial=False,
                            total_parts=0, chunks=[], total_lines=0, truncated=False)

    is_partial = any(p for _, p in candidate_files)
    total_parts = len(candidate_files)

    chunks = []
    for i, (file_path, _) in enumerate(candidate_files):
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        line_count = content.count("\n") + 1
        chunks.append(SourceChunk(
            class_name=class_name,
            file_path=str(file_path),
            is_partial=is_partial,
            part_index=i + 1,
            total_parts=total_parts,
            content=content,
            line_count=line_count,
        ))

    total_lines = sum(c.line_count for c in chunks)
    return SourceResult(
        class_name=class_name,
        is_partial=is_partial,
        total_parts=total_parts,
        chunks=chunks,
        total_lines=total_lines,
        truncated=False,
    )


def format_for_llm(result: SourceResult,
                   max_chars: int = 12000) -> str:
    """
    Converts SourceResult into a string for LLM consumption.
    If max_chars is exceeded, each file is truncated evenly.
    """
    if not result.chunks:
        return f"Could not find class `{result.class_name}`."

    lines = []

    if result.is_partial:
        lines.append(
            f"## `{result.class_name}` (partial class — {result.total_parts} files)\n"
        )
    else:
        lines.append(f"## `{result.class_name}` — Source Code\n")

    # Allowed characters per file
    chars_per_file = max_chars // max(len(result.chunks), 1)
    total_used = 0
    truncated = False

    for chunk in result.chunks:
        rel_path = _relative_path(chunk.file_path)
        header = (
            f"### File {chunk.part_index}/{chunk.total_parts}: {rel_path}"
            if result.is_partial
            else f"### File: {rel_path}"
        )
        lines.append(header)
        lines.append("```csharp")

        content = chunk.content
        if len(content) > chars_per_file:
            content = content[:chars_per_file]
            # Truncate to the last complete line
            last_newline = content.rfind("\n")
            if last_newline > 0:
                content = content[:last_newline]
            lines.append(content)
            lines.append("```")
            lines.append(
                f"⚠️ File is too long ({chunk.line_count} lines). "
                f"Displaying the first {content.count(chr(10))+1} lines only."
            )
            truncated = True
        else:
            lines.append(content)
            lines.append("```")

        total_used += len(content)
        lines.append("")

        if total_used >= max_chars:
            remaining = result.total_parts - chunk.part_index
            if remaining > 0:
                lines.append(
                    f"⚠️ Remaining {remaining} files omitted due to character limit."
                )
            truncated = True
            break

    if truncated:
        lines.append(
            f"\n> Only showing a part of the total {result.total_lines} lines. "
            "Please request again if you need specific methods or sections."
        )

    return "\n".join(lines)


def _relative_path(full_path: str) -> str:
    """Returns the relative path starting from the Scripts folder."""
    parts = Path(full_path).parts
    for i, part in enumerate(parts):
        if part.lower() in ("scripts", "assets", "src", "source"):
            return str(Path(*parts[i:]))
    return Path(full_path).name
