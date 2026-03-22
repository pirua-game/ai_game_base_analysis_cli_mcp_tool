"""
gdep.ue5_blueprint_mapping
Blueprint <-> C++ detailed mapping (UE5).

Extracts from .uasset binaries without running the editor:
  cpp_parent    - NativeParentClass (the C++ class this BP extends)
  bp_class      - Blueprint-generated _C class name
  event_nodes   - Entry points in the event graph (K2Node_Event_*)
  k2_overrides  - Overridden C++ blueprint-callable virtuals (K2_ prefix)
  node_flow     - Ordered function calls after each event entry point
  variables     - BP-declared variables with type hints
  asset_refs    - /Game/ asset paths referenced in this BP
  gameplay_tags - GameplayTag string values embedded in this BP
  gas_params    - GAS-specific config fields (ActivationOwnedTags, etc.)
  cpp_refs      - Additional C++ types used (beyond the direct parent)
"""
from __future__ import annotations

import os
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_IGNORE_DIRS = frozenset({
    "__ExternalActors__", "__ExternalObjects__",
    "Collections", "Developers",
})

_ENGINE_MODULES = frozenset({
    "CoreUObject", "Engine", "BlueprintGraph", "UnrealEd",
    "GameplayAbilities", "EnhancedInput", "SlateCore", "UMG",
    "InputCore", "AnimGraphRuntime", "AIModule", "NavigationSystem",
    "GameplayTasks", "ControlRig", "MovieScene", "KismetSystemLibrary",
    "KismetMathLibrary", "HeadMountedDisplay", "OnlineSubsystem",
})

_GAS_PARAM_NAMES = frozenset({
    "ActivationOwnedTags", "ActivationBlockedTags", "ActivationRequiredTags",
    "CancelAbilitiesWithTag", "BlockAbilitiesWithTag",
    "SourceBlockedTags", "TargetBlockedTags",
    "InstancingPolicy", "NetExecutionPolicy", "NetSecurityPolicy",
    "ReplicationPolicy",
})

# UE5 variable types we can detect from binary strings
_VAR_TYPES = (
    "AnimMontage", "AnimSequence", "AnimBlueprint",
    "GameplayTagContainer", "GameplayTag",
    "SoundBase", "SoundCue", "SoundWave",
    "ParticleSystem", "NiagaraSystem", "NiagaraComponent",
    "StaticMesh", "SkeletalMesh", "MaterialInterface", "Texture2D",
    "UInputAction", "InputAction", "UInputMappingContext", "InputMappingContext",
    "CurveFloat", "CurveTable", "DataTable",
    "float", "bool", "int32", "int64", "FVector", "FRotator",
)

# ---------------------------------------------------------------------------
# Compiled patterns  (built once at import time)
# ---------------------------------------------------------------------------

_SCRIPT_PAT         = re.compile(rb'/Script/(\w+)\.(\w+)')
_C_CLASS_PAT        = re.compile(rb'(?<!\w)([A-Z][A-Za-z_0-9]{2,}_C)\x00')
_NATIVE_PARENT_PAT  = re.compile(
    rb'NativeParentClass[\x00-\x3f]{1,60}/Script/(\w+)\.(\w+)', re.DOTALL)
_GAME_PATH_PAT      = re.compile(rb'(/Game/[\w/._-]{4,200})')
_GTAG_PAT           = re.compile(
    rb'"([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+){1,6})"')

# Event / K2 entry points
_EVENT_PAT = re.compile(
    rb'(?<!\w)(K2_\w+|Receive\w+|Execute_\w+|CustomEvent_?\w*)\x00')

# Node graph paths:  "EventGraph.K2Node_Event_0"
_NODE_KEY_PAT = re.compile(
    rb'(EventGraph|FunctionGraphs)\.(K2Node_\w+)\x00')

# K2Node_CallFunction references — ordered call list after each event
# Pattern: "K2Node_CallFunction_N" or just "FunctionName" near CallFunction
_CALL_FN_PAT = re.compile(
    rb'K2Node_CallFunction[_\d]*\x00[\x00-\x3f]{0,20}([\x21-\x7e]{3,60}?)\x00',
    re.DOTALL)

# Variable declarations: InternalVariableName <bytes> <name>
_VAR_PAT = re.compile(
    rb'InternalVariableName[\x00-\x3f]{1,16}([\x21-\x7e]{3,60}?)\x00')

# GAS params: param name <bytes> value
_GAS_PAT = re.compile(
    b'(' + b'|'.join(p.encode() for p in sorted(_GAS_PARAM_NAMES)) + b')'
    b'[\\x00-\\x3f]{1,30}([\\x21-\\x7e]{2,80}?)\\x00',
    re.DOTALL)

# Variable type hints — look for type keyword followed by prop/var name
_TYPED_VAR_PAT = re.compile(
    b'(' + b'|'.join(t.encode() for t in _VAR_TYPES) + b')'
    b'\\x00[\\x00-\\x3f]{0,12}([\\x21-\\x7e]{3,60}?)\\x00',
    re.DOTALL)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BPVariable:
    name: str
    type_hint: str = ""

@dataclass
class BPEventNode:
    name: str                # e.g. K2_ActivateAbility / ReceiveBeginPlay
    graph: str = ""          # EventGraph / FunctionGraphs
    node_key: str = ""       # K2Node_Event_0 etc.
    call_chain: list[str] = field(default_factory=list)  # ordered fn calls

@dataclass
class BlueprintMapping:
    asset_path:    str          # /Game/... path (no extension)
    asset_name:    str          # BP_GA_BasicAttack
    bp_class:      str          # BP_GA_BasicAttack_C
    cpp_parent:    str          # ARGamePlayAbility_BasicAttack
    cpp_module:    str          # HackAndSlash
    event_nodes:   list[BPEventNode]    = field(default_factory=list)
    k2_overrides:  list[str]            = field(default_factory=list)
    variables:     list[BPVariable]     = field(default_factory=list)
    asset_refs:    list[str]            = field(default_factory=list)
    gameplay_tags: list[str]            = field(default_factory=list)
    gas_params:    dict[str, str]       = field(default_factory=dict)
    cpp_refs:      list[str]            = field(default_factory=list)

@dataclass
class ProjectBlueprintMap:
    project_root: Path
    module_name:  str
    blueprints:   dict[str, BlueprintMapping]       = field(default_factory=dict)
    cpp_to_bps:   dict[str, list[BlueprintMapping]] = field(default_factory=dict)

# ---------------------------------------------------------------------------
# Module name auto-detection (samples uassets to find dominant /Script/X)
# ---------------------------------------------------------------------------

def _detect_module_from_assets(content_root: Path, hint: str) -> str:
    """
    Sample up to 20 non-LFS uassets concurrently and count /Script/X occurrences.
    Returns the most common non-engine module name, or `hint` as fallback.
    """
    samples: list[Path] = []
    for root, dirs, files in os.walk(content_root):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
        for fname in files:
            if fname.endswith('.uasset'):
                samples.append(Path(root) / fname)
        if len(samples) >= 20:
            break

    counter: Counter[str] = Counter()

    def _read_one(p: Path) -> list[str]:
        try:
            data = p.read_bytes()
            if data.startswith(b'version https://git-lfs'):
                return []
            return [m.group(1).decode('ascii', 'ignore')
                    for m in _SCRIPT_PAT.finditer(data)
                    if m.group(1).decode('ascii', 'ignore') not in _ENGINE_MODULES]
        except Exception:
            return []

    with ThreadPoolExecutor(max_workers=min(8, len(samples) or 1)) as pool:
        for mods in pool.map(_read_one, samples):
            counter.update(mods)

    return counter.most_common(1)[0][0] if counter else hint

# ---------------------------------------------------------------------------
# Per-asset extraction
# ---------------------------------------------------------------------------

def _parse_asset(asset_path: Path, content_root: Path,
                 module_name: str) -> BlueprintMapping | None:
    """Parse one .uasset and return a BlueprintMapping, or None if not a project BP."""
    try:
        data = asset_path.read_bytes()
    except Exception:
        return None

    # Skip Git LFS stubs
    if data.startswith(b'version https://git-lfs'):
        return None

    module_bytes = module_name.encode('ascii')

    # 1. C++ parent via NativeParentClass --------------------------------
    cpp_parent = ""
    cpp_module = ""
    nm = _NATIVE_PARENT_PAT.search(data)
    if nm:
        cpp_module = nm.group(1).decode('ascii', 'ignore')
        cpp_parent = nm.group(2).decode('ascii', 'ignore')

    # Fallback: first /Script/OurModule.ClassName reference
    if not cpp_parent:
        for sm in _SCRIPT_PAT.finditer(data):
            mod = sm.group(1).decode('ascii', 'ignore')
            cls = sm.group(2).decode('ascii', 'ignore')
            if mod == module_name and not cls.endswith('_C') and cls != 'Class':
                cpp_parent = cls
                cpp_module = mod
                break

    if not cpp_parent:
        return None  # not a project-specific blueprint

    # 2. BP-generated class name -----------------------------------------
    bp_class = ""
    stem = asset_path.stem
    for cm in _C_CLASS_PAT.finditer(data):
        name = cm.group(1).decode('ascii', 'ignore')
        if name.startswith(('Default__', 'SKEL_')):
            continue
        if stem in name:
            bp_class = name
            break
        if not bp_class:
            bp_class = name

    # 3. /Game/ path (relative from Content/) ----------------------------
    try:
        rel = asset_path.relative_to(content_root)
        game_path = '/Game/' + str(rel).replace('\\', '/').removesuffix('.uasset')
    except ValueError:
        game_path = '/Game/' + stem

    mapping = BlueprintMapping(
        asset_path=game_path,
        asset_name=stem,
        bp_class=bp_class,
        cpp_parent=cpp_parent,
        cpp_module=cpp_module,
    )
    _enrich(mapping, data, module_name)
    return mapping

def _enrich(mapping: BlueprintMapping, data: bytes, module_name: str) -> None:
    """Fill all detail fields of a BlueprintMapping from raw binary data."""

    # 4. Event entry points ----------------------------------------------
    seen_ev: set[str] = set()
    for em in _EVENT_PAT.finditer(data):
        name = em.group(1).decode('ascii', 'ignore')
        if name not in seen_ev and name not in ('EventGraph', 'EventReference'):
            seen_ev.add(name)
            mapping.event_nodes.append(BPEventNode(name=name))

    # 5. Node keys (graph.K2Node_Event_N) --------------------------------
    node_queue = list(mapping.event_nodes)  # assign graph/key in order
    for nk in _NODE_KEY_PAT.finditer(data):
        graph    = nk.group(1).decode('ascii', 'ignore')
        node_key = nk.group(2).decode('ascii', 'ignore')
        if node_queue:
            ev = node_queue.pop(0)
            ev.graph    = graph
            ev.node_key = node_key

    # K2 overrides = event nodes with K2_ prefix
    mapping.k2_overrides = sorted(
        ev.name for ev in mapping.event_nodes if ev.name.startswith('K2_'))

    # 6. Call chain after each event (K2Node_CallFunction references) ----
    # Collect all function calls in binary order → assign round-robin to events
    calls: list[str] = []
    seen_calls: set[str] = set()
    for cf in _CALL_FN_PAT.finditer(data):
        fn = cf.group(1).decode('ascii', 'ignore').strip()
        if (fn and fn not in seen_calls
                and not fn.startswith(('K2Node', 'Event', 'Default'))
                and len(fn) > 2):
            seen_calls.add(fn)
            calls.append(fn)

    # Distribute calls to the first event node (simplification: one event graph)
    if mapping.event_nodes and calls:
        mapping.event_nodes[0].call_chain = calls[:20]

    # 7. Variables (InternalVariableName) --------------------------------
    seen_vars: set[str] = set()
    for vm in _VAR_PAT.finditer(data):
        vname = vm.group(1).decode('ascii', 'ignore').strip()
        if vname and vname not in seen_vars and len(vname) > 2:
            seen_vars.add(vname)
            mapping.variables.append(BPVariable(name=vname))

    # 7b. Type hints from typed variable pattern -------------------------
    seen_typed: set[str] = set()
    for tv in _TYPED_VAR_PAT.finditer(data):
        type_hint = tv.group(1).decode('ascii', 'ignore')
        vname     = tv.group(2).decode('ascii', 'ignore').strip()
        if (vname and vname not in seen_typed and len(vname) > 2
                and not vname.startswith(('b', 'K2', 'Event'))):
            seen_typed.add(vname)
            # Try to match with existing variable or add new typed one
            matched = False
            for v in mapping.variables:
                if v.name == vname and not v.type_hint:
                    v.type_hint = type_hint
                    matched = True
                    break
            if not matched and vname not in seen_vars:
                mapping.variables.append(BPVariable(name=vname, type_hint=type_hint))
                seen_vars.add(vname)

    # 8. /Game/ asset references (excluding self) ------------------------
    seen_refs: set[str] = set()
    for gm in _GAME_PATH_PAT.finditer(data):
        ref = gm.group(1).decode('ascii', 'ignore')
        ref_clean = re.sub(r'\.(uasset|umap)$', '', ref)
        if mapping.asset_name not in ref_clean and ref_clean not in seen_refs:
            seen_refs.add(ref_clean)
            mapping.asset_refs.append(ref_clean)

    # 9. GameplayTag values ----------------------------------------------
    seen_tags: set[str] = set()
    for tm in _GTAG_PAT.finditer(data):
        tag = tm.group(1).decode('ascii', 'ignore')
        if '.' in tag and tag not in seen_tags:
            parts = tag.split('.')
            if all(re.match(r'^[A-Za-z][A-Za-z0-9_]*$', p) for p in parts):
                seen_tags.add(tag)
                mapping.gameplay_tags.append(tag)

    # 10. GAS parameters -------------------------------------------------
    for pm in _GAS_PAT.finditer(data):
        param = pm.group(1).decode('ascii', 'ignore')
        value = pm.group(2).decode('ascii', 'ignore').strip()
        if value:
            mapping.gas_params[param] = value

    # 11. Additional C++ type refs ---------------------------------------
    seen_cpp: set[str] = set()
    for sm in _SCRIPT_PAT.finditer(data):
        mod = sm.group(1).decode('ascii', 'ignore')
        cls = sm.group(2).decode('ascii', 'ignore')
        if mod not in _ENGINE_MODULES and cls not in seen_cpp:
            seen_cpp.add(cls)
            if cls != mapping.cpp_parent and not cls.endswith('_C'):
                mapping.cpp_refs.append(cls)

# ---------------------------------------------------------------------------
# LFS Fallback: filename-based catalogue when all uassets are Git LFS stubs
# ---------------------------------------------------------------------------

# BP 파일명 접두사 → 타입 분류
_BP_PREFIXES: list[tuple[str, str]] = [
    ('GA_',   'GameplayAbility'),
    ('GE_',   'GameplayEffect'),
    ('GC_',   'GameplayCue'),
    ('ABP_',  'AnimBlueprint'),
    ('AM_',   'AnimMontage'),
    ('W_',    'Widget'),
    ('UI_',   'Widget'),
    ('B_',    'Blueprint'),
    ('BFL_',  'FunctionLibrary'),
    ('DA_',   'DataAsset'),
    ('DT_',   'DataTable'),
]

def _classify_bp_name(stem: str) -> str:
    for prefix, label in _BP_PREFIXES:
        if stem.startswith(prefix):
            return label
    return 'Blueprint'


def _build_lfs_fallback(source_path: str, cpp_class: str | None = None) -> str:
    """
    Git LFS 포인터만 있는 프로젝트에서 파일명 기반으로 BP/ABP 목록을 제공합니다.
    Source 디렉터리의 C++ 클래스 이름과 파일명 유사도로 매핑을 시도합니다.
    """
    from .ue5_blueprint_refs import find_content_root

    content_root = find_content_root(source_path)
    if content_root is None:
        return "Content 폴더를 찾을 수 없습니다."

    # ── 1. uasset 파일 목록 수집 (LFS 포인터 여부 샘플 확인) ──────────────
    asset_files: list[Path] = []
    lfs_count   = 0
    sample_size = 0
    for root, dirs, files in os.walk(content_root):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
        for fname in files:
            if not fname.endswith('.uasset'):
                continue
            p = Path(root) / fname
            asset_files.append(p)
            if sample_size < 10:
                try:
                    head = p.read_bytes()[:40]
                    if head.startswith(b'version https://git-lfs'):
                        lfs_count += 1
                except Exception:
                    pass
                sample_size += 1

    is_lfs = lfs_count > sample_size // 2

    # ── 2. C++ 클래스 목록 (Source 디렉터리에서) ─────────────────────────
    cpp_classes: set[str] = set()
    proj_root = content_root.parent
    source_root = proj_root / 'Source'
    if source_root.exists():
        for root, dirs, files in os.walk(source_root):
            for fname in files:
                if fname.endswith('.h'):
                    stem = Path(fname).stem
                    cpp_classes.add(stem)

    # ── 3. 파일명 → 타입별 그룹핑 ─────────────────────────────────────────
    groups: dict[str, list[str]] = {}
    for p in asset_files:
        stem  = p.stem
        label = _classify_bp_name(stem)
        groups.setdefault(label, []).append(stem)

    for label in groups:
        groups[label].sort()

    # ── 4. cpp_class 필터 모드 ─────────────────────────────────────────────
    if cpp_class:
        # 이름 유사도 기반 — cpp_class 의 핵심 부분을 포함하는 BP 찾기
        bare = cpp_class
        for prefix in ('A', 'U', 'F', 'I', 'E'):
            if cpp_class.startswith(prefix):
                bare = cpp_class[1:]
                break
        bare_lower = bare.lower()

        matched: list[tuple[str, str]] = []
        for p in asset_files:
            stem_lower = p.stem.lower()
            # 핵심 단어가 파일명에 포함되는 경우
            if bare_lower in stem_lower or stem_lower.replace('_', '') in bare_lower.replace('_', ''):
                matched.append((p.stem, _classify_bp_name(p.stem)))

        lines = [
            f"# Blueprint search for `{cpp_class}` (LFS mode — filename matching)",
            "> ⚠️ Git LFS 포인터 프로젝트입니다. 파일명 유사도 기반 결과입니다.\n",
        ]
        if matched:
            lines.append(f"## 매칭된 에셋 ({len(matched)}개)\n")
            for stem, label in matched[:40]:
                lines.append(f"  - `{stem}` [{label}]")
            if len(matched) > 40:
                lines.append(f"  ... +{len(matched)-40} more")
        else:
            lines.append(f"`{cpp_class}` 와 유사한 이름의 Blueprint를 찾지 못했습니다.")
            lines.append("\n전체 BP 목록은 cpp_class 없이 조회하세요.")
        return "\n".join(lines)

    # ── 5. 전체 목록 모드 ─────────────────────────────────────────────────
    total = len(asset_files)
    lfs_note = "⚠️ Git LFS 포인터 프로젝트" if is_lfs else ""
    lines = [
        f"# Blueprint Catalogue [{proj_root.name}]  {lfs_note}",
        f"  Total .uasset files: {total}",
        f"  C++ header files (Source): {len(cpp_classes)}",
        "",
        "> Git LFS 포인터 파일만 있어 바이너리 파싱이 불가합니다.",
        "> 파일명 패턴 기반 분류 결과를 제공합니다.\n",
    ]

    for label, stems in sorted(groups.items()):
        if not stems:
            continue
        lines.append(f"## {label} ({len(stems)}개)")
        for stem in stems[:30]:
            lines.append(f"  - `{stem}`")
        if len(stems) > 30:
            lines.append(f"  ... +{len(stems)-30} more")
        lines.append("")

    if cpp_classes:
        lines.append(f"## C++ 클래스 목록 (Source, {len(cpp_classes)}개)")
        for cls in sorted(cpp_classes)[:40]:
            lines.append(f"  - `{cls}`")
        if len(cpp_classes) > 40:
            lines.append(f"  ... +{len(cpp_classes)-40} more")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry: build full project BP map
# ---------------------------------------------------------------------------

def _bp_map_to_dict(bp_map: ProjectBlueprintMap) -> dict:
    import dataclasses
    d = dataclasses.asdict(bp_map)
    d["project_root"] = str(bp_map.project_root)
    return d


def _bp_map_from_dict(d: dict) -> ProjectBlueprintMap:
    def _ev(x):  return BPEventNode(**{k: v for k, v in x.items()
                                       if k in BPEventNode.__dataclass_fields__})
    def _var(x): return BPVariable(**{k: v for k, v in x.items()
                                      if k in BPVariable.__dataclass_fields__})
    def _bp(x):
        evs  = [_ev(e) for e in x.pop("event_nodes", [])]
        vars_ = [_var(v) for v in x.pop("variables", [])]
        return BlueprintMapping(
            **{k: v for k, v in x.items() if k in BlueprintMapping.__dataclass_fields__},
            event_nodes=evs, variables=vars_,
        )

    bps_dict = {k: _bp(v) for k, v in d.get("blueprints", {}).items()}
    cpp_dict: dict[str, list[BlueprintMapping]] = {}
    for cpp_cls, lst in d.get("cpp_to_bps", {}).items():
        cpp_dict[cpp_cls] = [_bp(x) for x in lst]
    return ProjectBlueprintMap(
        project_root=Path(d["project_root"]),
        module_name=d["module_name"],
        blueprints=bps_dict,
        cpp_to_bps=cpp_dict,
    )


def _build_bp_map_raw(source_path: str, progress_cb=None) -> ProjectBlueprintMap:
    """
    Scan all .uasset files under the project Content folder and build a full
    Blueprint <-> C++ mapping.

    Args:
        source_path:  UE5 Source folder OR project root.
        progress_cb:  Optional callable(done: int, total: int).
    Returns:
        ProjectBlueprintMap with .blueprints and .cpp_to_bps populated.
    """
    from .ue5_blueprint_refs import detect_module_name, find_content_root

    content_root = find_content_root(source_path)
    if content_root is None:
        return ProjectBlueprintMap(project_root=Path(source_path),
                                   module_name="Unknown")

    # Detect module name — first try .uproject heuristic, then confirm with
    # uasset sampling to handle Lyra-style projects where module != project name.
    # Sampling is done concurrently to avoid blocking the main scan.
    hint_module = detect_module_name(source_path)
    module_name = _detect_module_from_assets(content_root, hint_module)

    bp_map = ProjectBlueprintMap(
        project_root=content_root.parent,
        module_name=module_name,
    )

    # Collect .uasset files (skip .umap — maps rarely define BPs)
    asset_files: list[Path] = []
    for root, dirs, files in os.walk(content_root):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
        for fname in files:
            if fname.endswith('.uasset'):
                asset_files.append(Path(root) / fname)

    total     = len(asset_files)
    completed = [0]

    max_workers = min(16, (os.cpu_count() or 4) * 2)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_parse_asset, p, content_root, module_name): p
                   for p in asset_files}
        for fut in as_completed(futures):
            completed[0] += 1
            if progress_cb:
                progress_cb(completed[0], total)
            try:
                mapping = fut.result()
            except Exception:
                continue
            if not mapping:
                continue

            key = mapping.bp_class or mapping.asset_name
            bp_map.blueprints[key] = mapping

            # Reverse index: cpp_parent → BPs
            bp_map.cpp_to_bps.setdefault(mapping.cpp_parent, []).append(mapping)
            # Also index with/without UE prefix (A/U stripped or added)
            for prefix in ('A', 'U', 'F', 'I', 'E'):
                if mapping.cpp_parent.startswith(prefix):
                    bare = mapping.cpp_parent[1:]
                    bp_map.cpp_to_bps.setdefault(bare, []).append(mapping)

    return bp_map


def build_bp_map(source_path: str, progress_cb=None) -> ProjectBlueprintMap:
    """
    Cached wrapper around _build_bp_map_raw.
    Warm hits skip all uasset I/O via mtime fingerprint cache.
    """
    from .uasset_cache import fingerprint_content, load_cache, save_cache
    from .ue5_blueprint_refs import find_content_root
    content_root = find_content_root(source_path)
    roots = [content_root] if content_root else []
    fp = fingerprint_content(roots)
    cache_key = "bp_map"
    cached = load_cache(source_path, cache_key)
    if cached and cached.get("_fp") == fp:
        try:
            return _bp_map_from_dict(cached["data"])
        except Exception:
            pass
    bp_map = _build_bp_map_raw(source_path, progress_cb)
    save_cache(source_path, cache_key,
               {"_fp": fp, "data": _bp_map_to_dict(bp_map)})
    return bp_map
# ---------------------------------------------------------------------------

def format_mapping(m: BlueprintMapping) -> str:
    lines = [
        f"## Blueprint: `{m.asset_name}`",
        f"  Path:       {m.asset_path}",
        f"  BP class:   `{m.bp_class}`",
        f"  C++ parent: `{m.cpp_parent}` (module: {m.cpp_module})",
    ]

    if m.event_nodes:
        lines.append("\n### Event Graph Entry Points")
        for ev in m.event_nodes:
            loc = f"  [{ev.graph} / {ev.node_key}]" if ev.graph else ""
            lines.append(f"  - `{ev.name}`{loc}")
            if ev.call_chain:
                lines.append("    Call chain:")
                for fn in ev.call_chain[:12]:
                    lines.append(f"      -> `{fn}`")
                if len(ev.call_chain) > 12:
                    lines.append(f"      ... +{len(ev.call_chain)-12} more")

    if m.k2_overrides:
        lines.append("\n### C++ Virtuals Overridden in BP (K2_)")
        for k in m.k2_overrides:
            lines.append(f"  - `{k}`")

    if m.variables:
        lines.append(f"\n### BP Variables ({len(m.variables)})")
        for v in m.variables[:20]:
            hint = f"  [{v.type_hint}]" if v.type_hint else ""
            lines.append(f"  - `{v.name}`{hint}")
        if len(m.variables) > 20:
            lines.append(f"  ... and {len(m.variables)-20} more")

    if m.gameplay_tags:
        lines.append(f"\n### GameplayTags ({len(m.gameplay_tags)})")
        for t in m.gameplay_tags[:15]:
            lines.append(f"  - `{t}`")

    if m.gas_params:
        lines.append("\n### GAS Parameters")
        for k, v in m.gas_params.items():
            lines.append(f"  - {k}: `{v}`")

    if m.asset_refs:
        lines.append(f"\n### Referenced Assets ({len(m.asset_refs)})")
        for r in m.asset_refs[:15]:
            lines.append(f"  - `{r}`")
        if len(m.asset_refs) > 15:
            lines.append(f"  ... and {len(m.asset_refs)-15} more")

    if m.cpp_refs:
        lines.append(f"\n### Additional C++ Types ({len(m.cpp_refs)})")
        lines.append("  " + ", ".join(f"`{c}`" for c in m.cpp_refs[:12]))

    return "\n".join(lines)


def format_cpp_to_bps(cpp_class: str, bps: list[BlueprintMapping]) -> str:
    if not bps:
        return f"No Blueprint implementations found for `{cpp_class}`."
    lines = [
        f"## Blueprint implementations of `{cpp_class}` ({len(bps)} found)\n",
    ]
    for m in bps:
        overrides = ", ".join(f"`{k}`" for k in m.k2_overrides) or "(none)"
        lines.append(f"### `{m.asset_name}` ({m.bp_class})")
        lines.append(f"  Path: {m.asset_path}")
        lines.append(f"  K2 overrides: {overrides}")
        if m.event_nodes:
            for ev in m.event_nodes:
                chain_str = ""
                if ev.call_chain:
                    chain_str = " -> " + " -> ".join(ev.call_chain[:5])
                    if len(ev.call_chain) > 5:
                        chain_str += f" (+{len(ev.call_chain)-5})"
                lines.append(f"  Event `{ev.name}`{chain_str}")
        if m.variables:
            typed = [v for v in m.variables if v.type_hint]
            if typed:
                lines.append("  Variables: " +
                             ", ".join(f"`{v.name}[{v.type_hint}]`"
                                       for v in typed[:5]))
        if m.gameplay_tags:
            lines.append(f"  Tags: {', '.join(m.gameplay_tags[:4])}")
        lines.append("")
    return "\n".join(lines)


def format_full_project_map(bp_map: ProjectBlueprintMap,
                             cpp_class: str | None = None) -> str:
    if cpp_class:
        candidates = [cpp_class]
        for prefix in ('A', 'U', 'F', 'I', 'E'):
            if cpp_class.startswith(prefix):
                candidates.append(cpp_class[1:])
            else:
                candidates.append(prefix + cpp_class)
        bps: list[BlueprintMapping] = []
        seen: set[str] = set()
        for c in candidates:
            for m in bp_map.cpp_to_bps.get(c, []):
                if m.bp_class not in seen:
                    seen.add(m.bp_class)
                    bps.append(m)
        return format_cpp_to_bps(cpp_class, bps)

    lines = [
        f"# Blueprint <-> C++ Map  [{bp_map.module_name}]",
        f"  Total blueprints: {len(bp_map.blueprints)}",
        f"  C++ classes with BP implementations: {len(bp_map.cpp_to_bps)}\n",
    ]
    for cpp_cls, bps in sorted(bp_map.cpp_to_bps.items()):
        # Only show prefixed canonical names (skip bare duplicates)
        if any(cpp_cls == b.cpp_parent for b in bps):
            names = ", ".join(f"`{b.asset_name}`" for b in bps[:5])
            extra = f" +{len(bps)-5} more" if len(bps) > 5 else ""
            lines.append(f"- `{cpp_cls}` -> {names}{extra}")
    return "\n".join(lines)
