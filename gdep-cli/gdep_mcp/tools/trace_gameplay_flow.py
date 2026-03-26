"""
gdep-mcp/tools/trace_gameplay_flow.py

High-level tool: 메서드 호출 체인 추적 + 핵심 노드 소스코드 발췌.
runner.flow + runner.read_source 결합.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_GDEP_ROOT = Path(__file__).parent.parent.parent
if str(_GDEP_ROOT) not in sys.path:
    sys.path.insert(0, str(_GDEP_ROOT))

from gdep import runner
from gdep.confidence import ConfidenceTier, confidence_footer
from gdep.detector import detect


def run(project_path: str, class_name: str, method_name: str,
        depth: int = 4, include_source: bool = True) -> str:
    """
    Trace the full execution flow of a gameplay method and show relevant source code.

    Builds a call tree starting from CLASS_NAME.METHOD_NAME, then fetches
    source snippets for key nodes to give the LLM actionable context.

    Use this tool to:
    - Debug a bug by tracing the execution path
    - Understand what a feature actually does at runtime
    - Identify async chains, locks, or dynamic dispatches in a flow

    Args:
        project_path:   Absolute path to the project Scripts/Source directory.
        class_name:     Entry-point class name. Example: "ManagerBattle", "AHSCharacterBase"
        method_name:    Entry-point method name. Example: "PlayHand", "BeginPlay"
        depth:          How many call levels to trace. Default: 4. Max recommended: 6.
        include_source: If True, appends source code of the entry-point class.
                        Set False to get only the flow tree (faster).

    Returns:
        A structured call flow tree followed by relevant source code excerpts.
    """
    try:
        profile = detect(project_path)
        sections: list[str] = []

        # ── Flow Analysis ────────────────────────────────────────────
        flow_result = runner.flow(profile, class_name, method_name,
                                  depth=depth, fmt="json")
        sections.append(f"## Call Flow: {class_name}.{method_name}  (depth={depth})")

        if flow_result.ok:
            try:
                raw = flow_result.stdout
                j = raw.find("{")
                data = json.loads(raw[j:]) if j >= 0 else {}
                nodes = data.get("nodes", [])
                edges = data.get("edges", [])
                # Guard: remove self-edges unconditionally (older server cache safety net)
                edges = [e for e in edges if e.get("from") != e.get("to")]
                bp_bridge = data.get("bpBridge", False)
                if bp_bridge:
                    sections.append("  > Blueprint bridge active: C++ flow continues into Blueprint implementation")

                # Format as readable tree text
                # Use entryClass from JSON (may differ from input if class name was normalized)
                actual_class = data.get("entryClass", class_name)
                sections.append(_render_flow_tree(nodes, edges, actual_class, method_name))

                dispatches = data.get("dispatches", [])
                if dispatches:
                    sections.append("\n### Dynamic Dispatches")
                    for d in dispatches:
                        sections.append(f"  ⇢ {d.get('handler', '?')}  (from {d.get('from','?')})")
            except (json.JSONDecodeError, TypeError):
                # Fallback: raw console output
                flow_console = runner.flow(profile, class_name, method_name,
                                           depth=depth, fmt="console")
                sections.append(flow_console.stdout if flow_console.ok else flow_result.stdout)
        else:
            sections.append(f"Flow trace failed: {flow_result.error_message}")

        # ── Source Code ──────────────────────────────────────────────
        if include_source:
            src_result = runner.read_source(profile, class_name, max_chars=6000)
            sections.append(f"\n## Source: {class_name}")
            if src_result.ok:
                sections.append(src_result.stdout)
            else:
                sections.append(f"Source not available: {src_result.error_message}")

        return "\n".join(sections) + confidence_footer(ConfidenceTier.HIGH, "source-level call graph")

    except Exception as e:
        return f"[trace_gameplay_flow] Error: {e}"


def _render_flow_tree(nodes: list, edges: list, root_class: str, root_method: str) -> str:
    """JSON nodes+edges → readable tree string."""
    if not nodes:
        return "  (No call nodes found — method may be empty or not parsed)"

    # Build adjacency map, condition map, and multiplicity map
    children: dict[str, list[str]] = {n["id"]: [] for n in nodes}
    condition_map:    dict[tuple[str, str], str] = {}
    multiplicity_map: dict[tuple[str, str], int] = {}
    for e in edges:
        frm, to = e.get("from", ""), e.get("to", "")
        if frm in children:
            children[frm].append(to)
        cond = e.get("condition", "")
        if cond:
            condition_map[(frm, to)] = cond
        mult = e.get("multiplicity", 1)
        if mult > 1:
            multiplicity_map[(frm, to)] = mult

    node_map = {n["id"]: n for n in nodes}
    entry_id = f"{root_class}.{root_method}"
    lines: list[str] = []
    visited_walk: set[str] = set()  # permanent — no revisits (handles cycles & self-edges)

    def _walk(nid: str, prefix: str = "", is_last: bool = True, parent_id: str = ""):
        if nid in visited_walk:
            return
        visited_walk.add(nid)
        node = node_map.get(nid)
        if node is None:
            return
        connector = "└── " if is_last else "├── "
        flags = ""
        if node.get("isAsync"):         flags += " async"
        if node.get("isLeaf"):          flags += " ○"
        if node.get("isDynamic"):       flags += " ⇢"
        if node.get("isBlueprintNode"): flags += " [BP]"
        label   = node.get("method", nid.split(".")[-1])
        cls     = node.get("class", "")
        display = f"{cls}.{label}" if cls and cls != root_class else label
        cond = condition_map.get((parent_id, nid), "")
        mult = multiplicity_map.get((parent_id, nid), 1)
        if mult > 1:
            flags += f" x{mult}"
        if cond:
            flags += f" ({cond})"
        lines.append(f"{prefix}{connector}{display}{flags}")
        # Skip self-edges; skip already-visited children
        kids = [k for k in children.get(nid, []) if k != nid and k not in visited_walk]
        child_prefix = prefix + ("    " if is_last else "│   ")
        for i, kid in enumerate(kids):
            _walk(kid, child_prefix, i == len(kids) - 1, nid)

    lines.append(f"└── {root_class}.{root_method}")
    for i, child_id in enumerate(children.get(entry_id, [])):
        _walk(child_id, "    ", i == len(children[entry_id]) - 1, entry_id)

    return "\n".join(lines)
