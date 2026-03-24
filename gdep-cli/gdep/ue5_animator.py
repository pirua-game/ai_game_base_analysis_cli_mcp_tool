"""
gdep.ue5_animator
UE5 AnimBlueprint (ABP) and Animation Montage analyzer.

Binary .uasset parsing — no UE Editor required.

ABP:
  - Detects AnimGraphNode_StateMachine, AnimGraphNode_Slot, AnimGraphNode_BlendSpacePlayer
  - Extracts state names (Idle, Walk/Run, Jump etc.) from binary strings
  - Finds AnimNotify class references (e.g. AnimNotify_FireProjectile → GAS link)
  - Identifies linked AnimSequence / BlendSpace / ControlRig assets

Montage:
  - Extracts SectionName strings (CompositeSection entries)
  - Extracts SlotName (DefaultSlot, FullBody, UpperBody etc.)
  - Finds AnimNotify events (especially AbilityTask notifies for GAS)
  - Identifies linked AnimSequence assets
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Binary patterns ───────────────────────────────────────────

# ABP detection — 바이너리 기반 (파일명 독립)
_ABP_PAT       = re.compile(rb'/Script/Engine\.AnimBlueprint\b|AnimBlueprintGeneratedClass')
_STATE_MACH    = re.compile(rb'AnimGraphNode_StateMachine|AnimNode_StateMachine')
_SLOT_NODE     = re.compile(rb'AnimGraphNode_Slot|AnimNode_Slot')
_BLENDSPACE    = re.compile(rb'AnimGraphNode_BlendSpacePlayer|AnimNode_BlendSpacePlayer|BlendSpace')
_CTRL_RIG      = re.compile(rb'AnimGraphNode_ControlRig|AnimNode_ControlRig|ControlRig')
_SEQ_PLAYER    = re.compile(rb'AnimGraphNode_SequencePlayer|AnimNode_SequencePlayer')
_SAVE_POSE     = re.compile(rb'AnimGraphNode_SaveCachedPose|AnimNode_SaveCachedPose')
_NOTIFY_PAT    = re.compile(rb'AnimNotify_\w+|AnimNotifyState_\w+')
_BAKED_SM      = re.compile(rb'BakedAnimationStateMachine')
_GAME_PATH_PAT = re.compile(rb'/Game/[\w/.\-]+')

# Montage detection — 바이너리 기반
_MONTAGE_PAT   = re.compile(rb'/Script/Engine\.AnimMontage\b')
_SECTION_PAT   = re.compile(rb'SectionName')
_SLOT_NAME_PAT = re.compile(rb'SlotName')
_COMPOSITE_SEC = re.compile(rb'CompositeSection')
_COMPOSITE_TRK = re.compile(rb'SlotAnimTracks|SlotAnimationTrack')
_NEXT_SECTION  = re.compile(rb'NextSectionName')
_ANIM_SEG      = re.compile(rb'AnimSegment')

_IGNORE_DIRS = {"__ExternalActors__", "__ExternalObjects__", "Collections", "Developers"}


# ── Data Models ───────────────────────────────────────────────

@dataclass
class ABPInfo:
    asset_name:     str
    asset_path:     str
    source_label:   str = "Project"               # "Project" | "Plugin/xxx"
    has_state_machine: bool = False
    has_blend_space:   bool = False
    has_control_rig:   bool = False
    has_slots:         bool = False
    state_names:    list[str] = field(default_factory=list)
    slot_names:     list[str] = field(default_factory=list)
    notify_classes: list[str] = field(default_factory=list)
    anim_refs:      list[str] = field(default_factory=list)
    gas_notifies:   list[str] = field(default_factory=list)


@dataclass
class MontageInfo:
    asset_name:    str
    asset_path:    str
    source_label:  str = "Project"               # "Project" | "Plugin/xxx"
    sections:      list[str] = field(default_factory=list)
    slot_names:    list[str] = field(default_factory=list)
    notify_events: list[str] = field(default_factory=list)    # AnimNotify names
    anim_refs:     list[str] = field(default_factory=list)    # Referenced AnimSequences
    gas_notifies:  list[str] = field(default_factory=list)    # GAS-related notifies


# ── GAS notify heuristics ─────────────────────────────────────

_GAS_NOTIFY_HINTS = (
    "Ability", "GAS", "GameplayAbility", "GameplayCue",
    "Effect", "Attack", "Fire", "Launch", "Activate",
    "ApplyEffect", "TriggerAbility", "Event",
)


def _is_gas_notify(name: str) -> bool:
    return any(h.lower() in name.lower() for h in _GAS_NOTIFY_HINTS)


# ── String extraction ─────────────────────────────────────────

def _ascii_strings(data: bytes, min_len: int = 4) -> list[str]:
    return [m.group().decode("ascii", "ignore")
            for m in re.finditer(rb'[\x20-\x7E]{' + str(min_len).encode() + rb',}', data)]


def _unique(lst: list[str]) -> list[str]:
    seen = set()
    return [x for x in lst if not (x in seen or seen.add(x))]


def _extract_verified_fstrings(data: bytes, min_len: int = 3, max_len: int = 64) -> list[str]:
    """
    Extract UE5 FString values where the length-prefix exactly matches the string length.
    UE5 FString format: int32 (LE) + ASCII bytes + null terminator.
    We verify the null terminator to avoid false positives from random int sequences.
    """
    import struct
    results: list[str] = []
    seen: set[str] = set()
    i = 0
    while i < len(data) - 8:
        try:
            length = struct.unpack_from('<i', data, i)[0]
            if 1 <= length <= max_len:
                end = i + 4 + length
                if end <= len(data):
                    s_bytes  = data[i + 4: end - 1]
                    null_b   = data[end - 1: end]
                    # Strict validation: null terminator present + pure ASCII printable
                    if (null_b == b'\x00'
                            and len(s_bytes) >= min_len
                            and all(0x20 <= b <= 0x7E for b in s_bytes)):
                        s = s_bytes.decode('ascii')
                        if s not in seen:
                            seen.add(s)
                            results.append(s)
                        i = end      # skip forward past this string
                        continue
        except Exception:
            pass
        i += 1
    return results


# Keywords that appear in actual State/StateMachine names (user-defined, short)
_STATE_GAME_WORDS = {
    'Idle', 'Walk', 'Run', 'Jump', 'Land', 'Fall', 'Attack', 'Death',
    'Hit', 'Dodge', 'Cast', 'Aim', 'Crouch', 'Sprint', 'Slide', 'Roll',
    'Jog', 'Fly', 'Swim', 'Climb', 'Grab', 'Throw', 'Block', 'Parry',
    'Stagger', 'Knockback', 'Stunned', 'Dead', 'Spawn', 'Locomotion',
    'Fire', 'Shoot', 'Kick', 'Punch', 'Slash', 'Dash', 'Evade', 'Guard',
    'Stand', 'Sit', 'Attacking', 'Moving', 'Falling', 'Landing',
}

# Strings that look like State names but are UE-internal graph/node labels
_GRAPH_NOISE = {
    'Anim Graph', 'Event Graph', 'Macro Graph', 'Uber Graph',
    'Option 0', 'Option 1', 'Option 2', 'Option 3',
    'Entry', 'Result', 'Output',
}

# Tooltip/description patterns (long phrases → not State names)
_DESC_STARTS = (
    'The ', 'A ', 'An ', 'This ', 'Set ', 'Get ', 'If ', 'When ',
    'Whether ', 'Executed ', 'Always ', 'Skip ', 'Allow ', 'Reset ',
    'Transfer ', 'Create ', 'Can ', 'Input ', 'Output ', 'alpha ',
    'Reinitialize', 'Scale ', 'Start from', 'LOD ',
    # Node property labels (not State names)
    'Play Rate', 'Blend Space', 'Slot Name', 'Blend Weight',
    'Blend Time', 'Blend Type', 'Blend Mode', 'Blend Pose',
    'Blend Poses', 'Blend Masks', 'Blend Weights', 'Blend Profile',
    'Blend Settings', 'Blend Depth',
    'Loop Animation', 'Loop',
    'Start Position', 'Play Rate Basis',
    'Max Transitions', 'Max Iterations',
    'Reach Precision', 'Soft Alpha', 'Soft Percent',
    'Alpha Scale', 'Alpha Curve', 'Alpha Input',
    'Group Name', 'Group Role',
    'Layer Setup', 'Local Pose', 'Component Pose', 'Base Pose',
    'Internal Time', 'Ignore for',
    'Foot IK', 'Legs Definition',
    'Upper Body Layer',
    'Curve Blend', 'Mesh Space',
    'Root Space', 'Transition Type', 'Child Upate',
    'Custom Blend', 'Active Value',
    'Is Valid', 'Is Not Valid',
    'Is Falling', 'Is Attacking', 'Is Accelerating', 'Is in Air',
    'Ground Speed', 'Should Move', 'Movement Component',
    'Character Movement', 'Orient Rotation',
    'Rotation Last', 'Yaw Delta',
    'Asset User', 'Event Queue', 'Control Rig',
    'Lean intensity', 'Setting Yaw',
)


def _filter_state_names(strings: list[str]) -> list[str]:
    """
    Filter a list of FString values to keep only genuine State/StateMachine names.

    Strategy:
    1. Reject anything that looks like a UE graph label or tooltip
    2. Accept strings with spaces IF they look like human-given state names
       (short, game-word-containing, no long descriptions)
    3. Accept single-word strings IF they are in the game-word set
    """
    results: list[str] = []
    for s in strings:
        if s in _GRAPH_NOISE:
            continue
        if any(s.startswith(p) for p in _DESC_STARTS):
            continue
        # Too long = tooltip/description
        if len(s) > 30:
            continue

        has_space = ' ' in s
        if has_space:
            # Space-containing: must match NAME pattern and contain a game word
            if not re.match(r'^[A-Za-z0-9][A-Za-z0-9 /\-]+$', s):
                continue
            words = re.split(r'[ /\-]+', s)
            if not any(w in _STATE_GAME_WORDS or (w[0].isupper() and 3 <= len(w) <= 15)
                       for w in words if w):
                continue
            # Must not be all-lowercase (those are usually variable names)
            if s == s.lower():
                continue
        else:
            # No space: only accept known game words OR short CamelCase names
            # that look like state names (not UE internal identifiers)
            if s in _STATE_GAME_WORDS:
                pass  # Accept
            elif re.match(r'^[A-Z][a-z]+(?:[A-Z][a-z]+)*$', s) and len(s) <= 20:
                # CamelCase: accept if it contains a game word component
                components = re.findall(r'[A-Z][a-z]+', s)
                if not any(c in _STATE_GAME_WORDS for c in components):
                    continue
            else:
                continue

        results.append(s)
    return list(dict.fromkeys(results))  # deduplicate preserving order


# ── ABP scanning ─────────────────────────────────────────────

# State name candidates: title-case, short, no special chars
_STATE_NAME_WORD = re.compile(r'^[A-Z][a-zA-Z0-9 /\-]{1,30}$')
_ENGINE_NOISE = {
    # AnimGraph internal nodes
    "AnimGraph", "AnimBlueprint", "AnimBlueprintGeneratedClass",
    "AnimInstance", "AnimLayer", "AnimNodeData", "AnimNotify",
    "AnimGroupInfo", "AnimNodeFunctionRef", "AnimNodeStructData",
    "AnimSubsystemInstance", "AnimBlueprintFunction", "AnimClassInterface",
    "AnimationGraph", "AnimationGraphSchema", "AnimationStateGraph",
    "AnimationStateGraphSchema", "AnimationTransitionGraph",
    "AnimationTransitionSchema", "AnimationGroupReference",
    "AnimStateEntryNode", "AnimStateNode", "AnimStateTransitionNode",
    "AnimGroupRole", "AimOffsetBlendSpace", "AnimLegIKDefinition",
    "AnimLegIKData", "AnimMontage", "AnimSequence",
    # Baked/compact structures
    "BakedAnimationStateMachine", "BakedAnimationState",
    "BakedStateExitTransition", "BakedStateMachines",
    "AliasedStateNodes",
    # Generic UE/Blueprint noise
    "UAnimInstance", "Blueprint", "Object", "Actor", "Component",
    "Controller", "Character", "Player", "Game", "Level", "World",
    "Engine", "Script", "AsCharacter", "AssetUserData",
    "BaseRotation", "ArrayProperty", "ArrayIndex", "AccessIndex",
    "AutomaticRuleTriggerTime", "ActualAlpha", "Additive",
    "AlphaBlend", "AlphaBoolBlend", "AlphaCurveName", "AlphaInputType",
    "AlphaScaleBias", "AlphaScaleBiasClamp",
}


def _is_state_name_candidate(s: str) -> bool:
    if s in _ENGINE_NOISE:
        return False
    if not _STATE_NAME_WORD.match(s):
        return False
    # Must not be a camelCase identifier (allow spaces and / for "Walk / Run")
    if s[0].isupper() and not s.isupper() and 3 <= len(s) <= 25:
        return True
    return False


def _scan_abp(asset_path: Path) -> ABPInfo | None:
    try:
        data = asset_path.read_bytes()
    except Exception:
        return None

    if not _ABP_PAT.search(data):
        return None
    # Must be an actual ABP (has state machine or slot node)
    has_sm    = bool(_STATE_MACH.search(data))
    has_slot  = bool(_SLOT_NODE.search(data))
    has_bs    = bool(_BLENDSPACE.search(data))
    has_cr    = bool(_CTRL_RIG.search(data))

    if not (has_sm or has_slot):
        return None  # Probably just an AnimInstance reference, not an ABP

    info = ABPInfo(
        asset_name=asset_path.stem,
        asset_path=str(asset_path),
        has_state_machine=has_sm,
        has_blend_space=has_bs,
        has_control_rig=has_cr,
        has_slots=has_slot,
    )

    # ── State names: verified FString → game-word filter ──────────
    fstrings = _extract_verified_fstrings(data, min_len=3, max_len=40)
    info.state_names = _filter_state_names(fstrings)

    # Slot names — scan fstrings for known slot names
    known_slots = [s for s in fstrings if s in (
        "DefaultSlot", "FullBody", "UpperBody", "Arms", "Legs",
        "Face", "UpperBodyAdditive", "WeaponSlot",
    )]
    info.slot_names = _unique(known_slots)[:10]

    # AnimNotify classes
    notifies = _unique([
        m.decode("ascii","ignore") for m in _NOTIFY_PAT.findall(data)
    ])
    info.notify_classes = notifies[:20]
    info.gas_notifies   = [n for n in notifies if _is_gas_notify(n)]

    # Animation asset references
    game_refs = _unique([
        m.decode("ascii","ignore") for m in _GAME_PATH_PAT.findall(data)
        if m.endswith(b'.uasset') or
           any(kw in m for kw in [b'Anim', b'Montage', b'BlendSpace', b'BS_', b'AM_', b'ABP_'])
    ])
    info.anim_refs = game_refs[:20]

    return info


# ── Montage scanning ──────────────────────────────────────────

def _scan_montage(asset_path: Path) -> MontageInfo | None:
    try:
        data = asset_path.read_bytes()
    except Exception:
        return None

    if not _MONTAGE_PAT.search(data):
        return None

    info = MontageInfo(
        asset_name=asset_path.stem,
        asset_path=str(asset_path),
    )

    strings = _ascii_strings(data)

    # Section names — extract strings after "SectionName" occurrences
    # Pattern: SectionName\x00...<name> (4-byte length-prefixed string)
    section_names_raw = re.findall(
        rb'SectionName[^\x00]{0,16}([\x20-\x7E]{3,32})', data
    )
    info.sections = _unique([
        m.decode("ascii","ignore").strip() for m in section_names_raw
        if m.decode("ascii","ignore").strip().replace("_","").isalnum()
        and not m.startswith(b'Section')
    ])[:15]
    # Fallback known patterns
    if not info.sections:
        info.sections = [s for s in strings
                         if s in ("Default", "Start", "Hit", "End", "Loop",
                                  "Attack", "Cast", "Fire", "Death")][:10]

    # Slot names
    slot_raw = re.findall(rb'SlotName[^\x00]{0,16}([\x20-\x7E]{4,30})', data)
    info.slot_names = _unique([
        m.decode("ascii","ignore").strip() for m in slot_raw
        if m.decode("ascii","ignore").strip() in (
            "DefaultSlot", "FullBody", "UpperBody", "Arms", "Legs", "WeaponSlot")
    ])[:5]
    if not info.slot_names:
        known = [s for s in strings if s in ("DefaultSlot","FullBody","UpperBody","Arms")]
        info.slot_names = _unique(known)[:5]

    # AnimNotify events
    notifies = _unique([m.decode("ascii","ignore") for m in _NOTIFY_PAT.findall(data)])
    info.notify_events = notifies[:20]
    info.gas_notifies  = [n for n in notifies if _is_gas_notify(n)]

    # Referenced AnimSequences (linked sequence assets)
    game_refs = _unique([
        m.decode("ascii","ignore") for m in _GAME_PATH_PAT.findall(data)
    ])
    info.anim_refs = game_refs[:10]

    return info


# ── Project scanner ───────────────────────────────────────────

def _find_content_root(project_path: str) -> Path | None:
    p = Path(project_path).resolve()
    for parent in [p] + list(p.parents):
        content = parent / "Content"
        if content.is_dir():
            return content
    return None


def _is_lfs(path: Path) -> bool:
    """Git LFS 포인터 파일인지 확인."""
    try:
        return path.read_bytes()[:40].startswith(b'version https://git-lfs')
    except Exception:
        return False


def _find_all_content_roots(project_path: str) -> list[tuple[Path, str]]:
    """Content + Plugins/*/Content 루트를 모두 반환. (label: Project | Plugin:xxx)"""
    from .ue5_ai_analyzer import _find_all_content_roots as _shared
    return _shared(project_path)


def _collect_assets(project_path: str) -> tuple[list[ABPInfo], list[MontageInfo]]:
    all_roots = _find_all_content_roots(project_path)
    abps: list[ABPInfo] = []
    montages: list[MontageInfo] = []

    if not all_roots:
        return abps, montages

    for content_root, source_label in all_roots:
        if not content_root.exists():
            continue
        for root, dirs, files in os.walk(content_root):
            dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
            for fname in files:
                if not fname.endswith(".uasset"):
                    continue
                fpath = Path(root) / fname
                stem  = fpath.stem

                # Git LFS 포인터 — 스킵
                if _is_lfs(fpath):
                    continue

                # ── 바이너리 판별 (파일명 독립) ───────────────
                try:
                    chunk = fpath.read_bytes()[:2048]
                except Exception:
                    continue

                is_abp     = bool(_ABP_PAT.search(chunk) and
                                  (_STATE_MACH.search(chunk) or _SLOT_NODE.search(chunk)))
                is_montage = bool(_MONTAGE_PAT.search(chunk) and
                                  (_COMPOSITE_SEC.search(chunk) or _SECTION_PAT.search(chunk)))

                # fallback: 파일명 힌트 (바이너리 판별 실패 시)
                if not is_abp and not is_montage:
                    if stem.startswith("ABP_") or stem.startswith("AnimBP"):
                        info = _scan_abp(fpath)
                        if info:
                            info.source_label = source_label
                            abps.append(info)
                    elif stem.startswith("AM_") or stem.endswith("_Montage"):
                        info = _scan_montage(fpath)
                        if info:
                            info.source_label = source_label
                            montages.append(info)
                    continue

                if is_abp and stem not in [a.asset_name for a in abps]:
                    info = _scan_abp(fpath)
                    if info:
                        info.source_label = source_label
                        abps.append(info)
                elif is_montage and stem not in [m.asset_name for m in montages]:
                    info = _scan_montage(fpath)
                    if info:
                        info.source_label = source_label
                        montages.append(info)

    return abps, montages


def _anim_to_dict(abps: list[ABPInfo], montages: list[MontageInfo]) -> dict:
    import dataclasses
    return {
        "abps":     [dataclasses.asdict(a) for a in abps],
        "montages": [dataclasses.asdict(m) for m in montages],
    }


def _anim_from_dict(d: dict) -> tuple[list[ABPInfo], list[MontageInfo]]:
    abps = [ABPInfo(**{k: v for k, v in x.items()
                       if k in ABPInfo.__dataclass_fields__})
            for x in d.get("abps", [])]
    montages = [MontageInfo(**{k: v for k, v in x.items()
                               if k in MontageInfo.__dataclass_fields__})
                for x in d.get("montages", [])]
    return abps, montages


def _cached_collect(project_path: str) -> tuple[list[ABPInfo], list[MontageInfo]]:
    from .uasset_cache import fingerprint_content, load_cache, save_cache
    from .ue5_ai_analyzer import _find_all_content_roots
    roots = [r for r, _ in _find_all_content_roots(project_path)]
    fp = fingerprint_content(roots)
    cache_key = "anim_scan"
    cached = load_cache(project_path, cache_key)
    if cached and cached.get("_fp") == fp:
        try:
            return _anim_from_dict(cached["data"])
        except Exception:
            pass
    abps, montages = _collect_assets(project_path)
    save_cache(project_path, cache_key,
               {"_fp": fp, "data": _anim_to_dict(abps, montages)})
    return abps, montages


# ── Public API ────────────────────────────────────────────────

def _lfs_fallback_anim(project_path: str, asset_type: str) -> str:
    """LFS 포인터 프로젝트에서 파일명 기반 Animation 에셋 목록을 반환."""
    content_root = _find_content_root(project_path)
    if content_root is None:
        return "Content folder not found."

    abp_files: list[str] = []
    montage_files: list[str] = []

    for root, dirs, files in os.walk(content_root):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
        for fname in files:
            if not fname.endswith(".uasset"):
                continue
            stem = Path(fname).stem
            if stem.startswith("ABP_") or stem.startswith("AnimBP"):
                abp_files.append(stem)
            elif stem.startswith("AM_") or "Montage" in stem or stem.endswith("_Montage"):
                montage_files.append(stem)

    abp_files.sort()
    montage_files.sort()

    lines = [
        f"# Animation Assets [{Path(project_path).name}]",
        "> [!] Git LFS pointer project -- filename-based list (binary parsing unavailable)\n",
    ]
    if asset_type in ('all', 'abp'):
        lines.append(f"## AnimBlueprint (ABP_*) -- {len(abp_files)} assets")
        for s in abp_files[:50]:
            lines.append(f"  - `{s}`")
        if len(abp_files) > 50:
            lines.append(f"  ... +{len(abp_files)-50} more")
        lines.append("")
    if asset_type in ('all', 'montage'):
        lines.append(f"## Animation Montage (AM_*) -- {len(montage_files)} assets")
        for s in montage_files[:50]:
            lines.append(f"  - `{s}`")
        if len(montage_files) > 50:
            lines.append(f"  ... +{len(montage_files)-50} more")
        lines.append("")
    if not abp_files and not montage_files:
        lines.append("No assets matching ABP_ / AM_ pattern found.")
    return "\n".join(lines)


def analyze_abp(project_path: str, asset_name: str | None = None) -> str:
    abps, _ = _cached_collect(project_path)

    if not abps:
        # LFS fallback 시도
        fallback = _lfs_fallback_anim(project_path, 'abp')
        if "ABP_" in fallback or "AnimBP" in fallback:
            return fallback
        return f"No AnimBlueprint assets found under: {project_path}"

    if asset_name:
        abps = [a for a in abps
                if a.asset_name.lower() == asset_name.lower()
                or asset_name.lower() in a.asset_name.lower()]

    lines = ["# AnimBlueprint (ABP) Analysis", f"Project: {project_path}", ""]

    for abp in abps:
        src = f"  [{abp.source_label}]" if abp.source_label != "Project" else ""
        lines.append(f"## {abp.asset_name}{src}")
        lines.append(f"File: {abp.asset_path}")

        features = []
        if abp.has_state_machine: features.append("StateMachine")
        if abp.has_blend_space:   features.append("BlendSpace")
        if abp.has_control_rig:   features.append("ControlRig")
        if abp.has_slots:         features.append("Slots")
        if features:
            lines.append(f"Features: {', '.join(features)}")

        if abp.state_names:
            lines.append(f"\n### States / Poses ({len(abp.state_names)})")
            for s in abp.state_names:
                lines.append(f"  - {s}")

        if abp.slot_names:
            lines.append("\n### Animation Slots")
            for s in abp.slot_names:
                lines.append(f"  - {s}")

        if abp.gas_notifies:
            lines.append("\n### GAS-related Notifies ⚡")
            for n in abp.gas_notifies:
                lines.append(f"  - {n}")

        if abp.notify_classes:
            other_notifies = [n for n in abp.notify_classes if n not in abp.gas_notifies]
            if other_notifies:
                lines.append("\n### Other AnimNotify Classes")
                for n in other_notifies[:10]:
                    lines.append(f"  - {n}")

        if abp.anim_refs:
            lines.append("\n### Referenced Animation Assets")
            for r in abp.anim_refs[:10]:
                lines.append(f"  - {r}")

        lines.append("")

    return "\n".join(lines)


def analyze_montage(project_path: str, asset_name: str | None = None) -> str:
    _, montages = _cached_collect(project_path)

    if not montages:
        fallback = _lfs_fallback_anim(project_path, 'montage')
        if "AM_" in fallback or "Montage" in fallback:
            return fallback
        return f"No AnimMontage assets found under: {project_path}"

    if asset_name:
        montages = [m for m in montages
                    if m.asset_name.lower() == asset_name.lower()
                    or asset_name.lower() in m.asset_name.lower()]

    lines = ["# Animation Montage Analysis", f"Project: {project_path}", ""]

    for mont in montages:
        src = f"  [{mont.source_label}]" if mont.source_label != "Project" else ""
        lines.append(f"## {mont.asset_name}{src}")
        lines.append(f"File: {mont.asset_path}")

        if mont.sections:
            lines.append(f"\n### Sections ({len(mont.sections)})")
            for s in mont.sections:
                lines.append(f"  - {s}")

        if mont.slot_names:
            lines.append("\n### Slots")
            for s in mont.slot_names:
                lines.append(f"  - {s}")

        if mont.gas_notifies:
            lines.append("\n### GAS-related Notifies ⚡")
            for n in mont.gas_notifies:
                lines.append(f"  - {n}")

        if mont.notify_events:
            other = [n for n in mont.notify_events if n not in mont.gas_notifies]
            if other:
                lines.append("\n### Other Notify Events")
                for n in other[:10]:
                    lines.append(f"  - {n}")

        if mont.anim_refs:
            lines.append("\n### Referenced AnimSequences")
            for r in mont.anim_refs[:8]:
                lines.append(f"  - {r}")

        lines.append("")

    return "\n".join(lines)
