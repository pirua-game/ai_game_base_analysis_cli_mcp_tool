"""
gdep.unity_animator
Unity Animator Controller structure analyzer.

Parses .controller (Unity YAML) files to extract:
  - Layers
  - States (per layer)
  - Transitions (from/to, conditions)
  - Blend Trees and their motions
  - AnimationClip references
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Data Models ──────────────────────────────────────────────

@dataclass
class BlendTreeMotion:
    clip_name: str
    threshold: float = 0.0
    speed:     float = 1.0


@dataclass
class BlendTree:
    blend_type:  str          # 0=1D, 1=2D Simple, 2=2D FreeformDirectional, etc.
    blend_param: str          # Parameter name
    motions:     list[BlendTreeMotion] = field(default_factory=list)


@dataclass
class AnimatorState:
    name:        str
    file_id:     str
    clip_name:   str = ""     # Direct clip (if not a blend tree)
    blend_tree:  BlendTree | None = None
    speed:       float = 1.0
    transitions: list[str] = field(default_factory=list)  # Destination state names


@dataclass
class AnimatorLayer:
    name:     str
    index:    int
    states:   list[AnimatorState]   = field(default_factory=list)
    default_state: str = ""         # Default state name


@dataclass
class AnimatorController:
    name:        str
    file_path:   str
    parameters:  list[dict]         # [{name, type}]
    layers:      list[AnimatorLayer]


# ── Unity YAML Parsing Helpers ────────────────────────────────

_FILEOBJ_PAT = re.compile(r'\{fileID:\s*(-?\d+)(?:,\s*guid:\s*([0-9a-f]+))?\}')
_NAME_PAT    = re.compile(r'm_Name:\s*(.+)')
_STATEID_PAT = re.compile(r'm_State:\s*\{fileID:\s*(-?\d+)')


def _extract_blocks(text: str, tag: str) -> list[str]:
    """Extract all YAML document blocks for a given Unity object tag."""
    pattern = re.compile(rf'--- !u!\d+ &(-?\d+)\n{re.escape(tag)}:(.+?)(?=\n--- |\Z)', re.DOTALL)
    return [m.group(2) for m in pattern.finditer(text)]


def _get_value(block: str, key: str) -> str:
    """Get a simple key: value from a YAML block."""
    m = re.search(rf'{re.escape(key)}:\s*(.+)', block)
    return m.group(1).strip() if m else ""


def _get_block_id(text: str, tag: str) -> dict[str, str]:
    """Map fileID → raw block text for a given tag."""
    pattern = re.compile(
        rf'--- !u!\d+ &(-?\d+)\n{re.escape(tag)}:\n(.+?)(?=\n--- |\Z)', re.DOTALL
    )
    return {m.group(1): m.group(2) for m in pattern.finditer(text)}


# ── Core Parsing Logic ────────────────────────────────────────

def _parse_parameters(text: str) -> list[dict]:
    """Parse Animator parameters from the AnimatorController block."""
    params = []
    param_blocks = re.findall(
        r'm_Name:\s*(\S+).*?m_Type:\s*(\d+)', text, re.DOTALL
    )
    type_map = {"0": "Float", "1": "Int", "2": "Bool", "3": "Trigger", "9": "Bool"}
    for name, ptype in param_blocks[:50]:
        params.append({"name": name, "type": type_map.get(ptype, ptype)})
    return params


def _parse_blend_tree(block: str) -> BlendTree | None:
    """Parse a BlendTree block."""
    if "m_BlendParameter" not in block and "m_Motions" not in block:
        return None

    blend_type  = _get_value(block, "m_BlendType")
    blend_param = _get_value(block, "m_BlendParameter")
    if not blend_param:
        blend_param = _get_value(block, "m_BlendParameterY") or "?"

    bt = BlendTree(blend_type=blend_type, blend_param=blend_param)

    # Extract motions: list of {m_Motion: {fileID:...}, m_Threshold, m_TimeScale}
    motion_blocks = re.findall(
        r'm_Motion:\s*\{fileID:\s*(-?\d+)[^}]*\}.*?m_Threshold:\s*([\d.\-]+)',
        block, re.DOTALL
    )
    for fid, threshold in motion_blocks:
        bt.motions.append(BlendTreeMotion(
            clip_name=f"clip@{fid}",  # will be resolved later if possible
            threshold=float(threshold),
        ))

    return bt


def _parse_states(text: str) -> dict[str, AnimatorState]:
    """Parse all AnimatorState blocks, keyed by fileID."""
    state_map: dict[str, AnimatorState] = {}
    state_blocks = _get_block_id(text, "AnimatorState")

    for fid, block in state_blocks.items():
        name    = _get_value(block, "m_Name")
        speed   = float(_get_value(block, "m_Speed") or "1.0")

        # Direct motion (AnimationClip reference)
        clip_name = ""
        motion_m = re.search(r'm_Motion:\s*\{fileID:\s*(-?\d+)', block)
        if motion_m:
            fid_motion = motion_m.group(1)
            # fileID 0 means BlendTree (check later), others are clips
            if fid_motion != "0":
                clip_name = f"clip@{fid_motion}"

        # Blend tree check
        bt = None
        if "m_BlendParameter" in block or "m_Motions" in block:
            bt = _parse_blend_tree(block)

        # Outgoing transitions
        trans_fids = re.findall(r'm_Transitions:\s*(?:\n\s*- \{fileID: (\d+)\})+', block)
        # simpler approach:
        trans_fids = re.findall(r'- \{fileID: (\d+)\}',
                                block[block.find("m_Transitions:"):] if "m_Transitions:" in block else "")

        state = AnimatorState(
            name=name or f"State@{fid}",
            file_id=fid,
            clip_name=clip_name,
            blend_tree=bt,
            speed=speed,
        )
        state_map[fid] = state

    return state_map


def _parse_layers(text: str, state_map: dict[str, AnimatorState]) -> list[AnimatorLayer]:
    """Parse AnimatorController layers."""
    layers: list[AnimatorLayer] = []

    # Get the AnimatorController block
    ctrl_blocks = _extract_blocks(text, "AnimatorController")
    if not ctrl_blocks:
        return layers

    ctrl_block = ctrl_blocks[0]

    # Parse layers list
    layer_sections = re.split(r'm_Layer\b', ctrl_block)
    # Alternative: find m_Layers array
    layer_pat = re.compile(
        r'm_Name:\s*(\S+).*?m_StateMachine:\s*\{fileID:\s*(-?\d+)\}',
        re.DOTALL
    )

    # Find StateMachines
    sm_blocks = _get_block_id(text, "AnimatorStateMachine")

    layer_idx = 0
    # Try to extract layer names from controller block
    layer_names_section = ctrl_block[ctrl_block.find("m_AnimatorLayers:"):] if "m_AnimatorLayers:" in ctrl_block else ""

    # Match each layer's name + state machine fileID
    layer_matches = re.findall(
        r'm_Name:\s*(\S+)\s*\n.*?m_StateMachine:\s*\{fileID:\s*(-?\d+)\}',
        layer_names_section, re.DOTALL
    )

    if not layer_matches and sm_blocks:
        # Fallback: treat each state machine as a layer
        for sm_fid, sm_block in sm_blocks.items():
            sm_name = _get_value(sm_block, "m_Name") or f"Layer{layer_idx}"
            layer_matches.append((sm_name, sm_fid))

    for layer_name, sm_fid in layer_matches:
        sm_block = sm_blocks.get(sm_fid, "")
        layer = AnimatorLayer(name=layer_name, index=layer_idx)

        # Default state
        default_m = re.search(r'm_DefaultState:\s*\{fileID:\s*(-?\d+)\}', sm_block)
        if default_m:
            default_state = state_map.get(default_m.group(1))
            if default_state:
                layer.default_state = default_state.name

        # Child states
        child_state_fids = re.findall(r'm_State:\s*\{fileID:\s*(-?\d+)\}', sm_block)
        for sfid in child_state_fids:
            state = state_map.get(sfid)
            if state:
                layer.states.append(state)

        layers.append(layer)
        layer_idx += 1

    return layers


def _parse_controller_file(controller_path: Path) -> AnimatorController | None:
    """Parse a single .controller file."""
    try:
        text = controller_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    if "AnimatorController" not in text:
        return None

    # Parameters
    ctrl_blocks = _extract_blocks(text, "AnimatorController")
    params: list[dict] = []
    if ctrl_blocks:
        params = _parse_parameters(ctrl_blocks[0])

    # States
    state_map = _parse_states(text)

    # Layers
    layers = _parse_layers(text, state_map)

    # Fallback: if no layers parsed but we have states, group as single layer
    if not layers and state_map:
        layer = AnimatorLayer(name="Base Layer", index=0)
        layer.states = list(state_map.values())
        layers = [layer]

    return AnimatorController(
        name=controller_path.stem,
        file_path=str(controller_path),
        parameters=params,
        layers=layers,
    )


# ── Public API ────────────────────────────────────────────────

def _find_controllers(project_path: str,
                      controller_name: str | None = None) -> list[Path]:
    """Find .controller files in a Unity project."""
    root = Path(project_path).resolve()
    _IGNORE = {"Library", "Temp", "obj", "Packages", "node_modules", ".git", "ProjectSettings"}

    results: list[Path] = []
    for f in root.rglob("*.controller"):
        if any(part in _IGNORE for part in f.parts):
            continue
        if controller_name is None or f.stem.lower() == controller_name.lower():
            results.append(f)

    return results


def analyze_animator(project_path: str,
                     controller_name: str | None = None) -> str:
    """
    Analyze Unity Animator Controller(s) and return a structured summary.

    Args:
        project_path:    Unity project or Assets folder path.
        controller_name: Optional — only analyze the named controller.

    Returns:
        Structured text describing layers, states, and blend trees.
    """
    controllers_paths = _find_controllers(project_path, controller_name)

    if not controllers_paths:
        msg = (
            "No .controller files found"
            + (f" matching '{controller_name}'" if controller_name else "")
            + f" under: {project_path}"
        )
        return msg

    lines: list[str] = []

    for ctrl_path in controllers_paths[:10]:  # cap at 10 to avoid overwhelming output
        ctrl = _parse_controller_file(ctrl_path)
        if ctrl is None:
            lines.append(f"## {ctrl_path.name} — parse failed\n")
            continue

        lines.append(f"## Animator: {ctrl.name}")
        lines.append(f"File: {ctrl.file_path}")

        if ctrl.parameters:
            lines.append(f"\n### Parameters ({len(ctrl.parameters)})")
            for p in ctrl.parameters:
                lines.append(f"  - {p['name']}  ({p['type']})")

        if not ctrl.layers:
            lines.append("\n_(No layers detected)_")
        else:
            for layer in ctrl.layers:
                default_hint = f"  [Default: {layer.default_state}]" if layer.default_state else ""
                lines.append(f"\n### Layer {layer.index}: {layer.name}{default_hint}")
                lines.append(f"  States ({len(layer.states)}):")

                for state in layer.states:
                    default_mark = " ★" if state.name == layer.default_state else ""
                    if state.blend_tree:
                        bt = state.blend_tree
                        bt_type_map = {"0":"1D","1":"2D Simple","2":"2D Freeform","3":"Direct"}
                        bt_type = bt_type_map.get(bt.blend_type, bt.blend_type)
                        lines.append(
                            f"  - {state.name}{default_mark}  "
                            f"[BlendTree/{bt_type} param={bt.blend_param}, "
                            f"{len(bt.motions)} motions]"
                        )
                    elif state.clip_name:
                        lines.append(f"  - {state.name}{default_mark}  → {state.clip_name}")
                    else:
                        lines.append(f"  - {state.name}{default_mark}")

        lines.append("")

    if len(controllers_paths) > 10:
        lines.append(f"... and {len(controllers_paths)-10} more controllers not shown")

    return "\n".join(lines)
