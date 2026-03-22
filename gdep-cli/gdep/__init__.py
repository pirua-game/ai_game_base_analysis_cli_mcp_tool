"""
gdep — Unified CLI for Game/App Codebase Analysis
"""
from .detector import ProjectKind, ProjectProfile, detect
from .runner import (
    RunResult,
    describe,
    diff,
    find_gdep,
    flow,
    graph,
    read_source,
    run,
    scan,
)
from .source_reader import find_class_files, format_for_llm

__all__ = [
    "detect", "ProjectProfile", "ProjectKind",
    "run", "scan", "flow", "describe", "graph", "diff",
    "read_source", "find_gdep", "RunResult",
    "find_class_files", "format_for_llm",
]
