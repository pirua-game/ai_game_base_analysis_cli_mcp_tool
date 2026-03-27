"""
gdep-mcp/tools/find_call_path.py

Two-point connection trace: find the shortest call path from method A to method B.
Uses BFS on the forward call graph.
"""
from __future__ import annotations

import sys
from pathlib import Path

_GDEP_ROOT = Path(__file__).parent.parent.parent
if str(_GDEP_ROOT) not in sys.path:
    sys.path.insert(0, str(_GDEP_ROOT))

from gdep import runner
from gdep.confidence import ConfidenceTier, confidence_footer
from gdep.detector import detect


def run(project_path: str, from_class: str, from_method: str,
        to_class: str, to_method: str, depth: int = 10) -> str:
    """
    Find the shortest call path between two methods.

    Args:
        project_path: Absolute path to Scripts/Source directory.
        from_class:   Source class name. E.g. "UIBattle"
        from_method:  Source method name. E.g. "OnClickPlayingCard"
        to_class:     Target class name. E.g. "ManagerBattle"
        to_method:    Target method name. E.g. "PlayHand"
        depth:        Max search depth (default 10).

    Returns:
        Call path chain: A.m1 → B.m2 [condition] → C.m3
    """
    try:
        profile = detect(project_path)
        result = runner.path(profile, from_class, from_method,
                             to_class, to_method, depth=depth)

        if not result.ok:
            return f"Error: {result.error_message}"

        return result.stdout.strip() + confidence_footer(
            ConfidenceTier.HIGH, "BFS on source-level call graph"
        )

    except Exception as e:
        return f"[find_call_path] Error: {e}"
