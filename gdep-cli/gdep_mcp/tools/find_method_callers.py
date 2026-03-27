"""
gdep-mcp/tools/find_method_callers.py

Reverse call graph: find all methods that call a specific method.
Thin wrapper around existing runner.method_impact().
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


def run(project_path: str, class_name: str, method_name: str) -> str:
    """
    Find all methods that call class_name::method_name (reverse call graph).

    Args:
        project_path: Absolute path to Scripts/Source directory.
        class_name:   Class containing the target method.
        method_name:  Method to find callers of.

    Returns:
        Structured list of caller methods with call conditions.
    """
    try:
        profile = detect(project_path)
        result = runner.method_impact(profile, class_name, method_name)

        if not result.ok:
            return f"Error: {result.error_message}"

        # Parse CLI output:
        #   "── Method Impact: Class::Method ──"
        #   "Called by N method(s):"
        #   "  ← CallerClass::CallerMethod [condition]"
        lines = result.stdout.strip().splitlines()
        callers: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("\u2190"):  # ← character
                callers.append(stripped)

        sections = [f"## Callers of {class_name}::{method_name}"]
        if not callers:
            sections.append(f"No callers found for {class_name}.{method_name}")
        else:
            sections.append(f"Found **{len(callers)}** caller(s):\n")
            for c in callers:
                sections.append(f"  {c}")

        return "\n".join(sections) + confidence_footer(
            ConfidenceTier.HIGH, "source-level reverse call graph"
        )

    except Exception as e:
        return f"[find_method_callers] Error: {e}"
