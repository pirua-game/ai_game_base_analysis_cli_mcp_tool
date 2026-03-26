"""
gdep.ue5_gas_analyzer
UE5 Gameplay Ability System (GAS) analysis.

Two-pass approach:
  1. C++ source scan — extract class declarations, UPROPERTY/UFUNCTION with GAS types
  2. .uasset binary scan — extract GameplayTag strings, GA/GE/AS class references

No UE Editor required — pure offline parsing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── GAS-specific patterns ─────────────────────────────────────

# C++ patterns — allow optional MODULE_API macro between 'class' and class name
# e.g.  class HACKANDSLASH_API UARGamePlayAbility_BasicAttack : public UGameplayAbility
_API_OPT       = r'(?:\s+\w+_API)?'
_GA_BASE_PAT   = re.compile(r'class' + _API_OPT + r'\s+\w+\s*:\s*(?:public\s+)?UGameplayAbility\b')
_GE_BASE_PAT   = re.compile(r'class' + _API_OPT + r'\s+\w+\s*:\s*(?:public\s+)?UGameplayEffect\b')
_AS_BASE_PAT   = re.compile(r'class' + _API_OPT + r'\s+\w+\s*:\s*(?:public\s+)?(?:UAttributeSet|FGameplayAttributeData)\b')
_ASC_USE_PAT   = re.compile(r'UAbilitySystemComponent\b')
_ENUM_CLS_PAT  = re.compile(r'\benum\s+class\s+(\w+)')
_TAG_DECL_PAT  = re.compile(r'FGameplayTag(?:Container)?\s+(\w+)')
_TAG_MACRO_PAT = re.compile(r'GAMEPLAYTAG_DECLARE_TAG\s*\(\s*(\w+(?:\.\w+)*)\s*\)')
# C++ runtime tag literals: RequestGameplayTag(TEXT("State.Attacking")) etc.
_REQUEST_TAG_PAT = re.compile(
    r'RequestGameplayTag\s*\(\s*(?:(?:TEXT|FName)\s*\(\s*)?["\']([A-Za-z][A-Za-z0-9.]*)["\']'
)

# Any class declaration: captures (child, parent) for transitive inheritance resolution
_CLS_DECL_PAT = re.compile(
    r'class\s+(?:\w+_API\s+)?(\w+)\s*:\s*(?:public\s+)?(\w+)'
)

# GAS root classes → kind string (used in 2-pass scan)
_GAS_ROOT_KIND: dict[str, str] = {
    "UGameplayAbility": "Ability",
    "UGameplayEffect":  "Effect",
    "UAttributeSet":    "AttributeSet",
}

# UPROPERTY holding GAS types — `class` 키워드 optional 처리
_UPROP_GA_PAT  = re.compile(
    r'UPROPERTY[^;]*?TSubclassOf\s*<\s*(?:class\s+)?(\w*GameplayAbility\w*)\s*>.*?(\w+)\s*;',
    re.DOTALL
)
_UPROP_GE_PAT  = re.compile(
    r'UPROPERTY[^;]*?TSubclassOf\s*<\s*(?:class\s+)?(\w*GameplayEffect\w*)\s*>.*?(\w+)\s*;',
    re.DOTALL
)

# .uasset binary patterns
_TAG_STRING_PAT  = re.compile(rb'([A-Za-z][A-Za-z0-9]*(?:\.[A-Za-z][A-Za-z0-9]*){1,5})')
_MODULE_CLS_PAT  = re.compile(rb'/Script/(\w+)\.(\w+)')
_GA_BIN_PAT      = re.compile(rb'GameplayAbility')
_GE_BIN_PAT      = re.compile(rb'GameplayEffect')
_AS_BIN_PAT      = re.compile(rb'AttributeSet')
_ABP_BIN_PAT     = re.compile(rb'AnimBlueprint|AnimInstance')
_BT_BIN_PAT      = re.compile(rb'BehaviorTree|BTTask|BTDecorator|BTService')

# Blueprint asset name patterns — GA_*/GE_*/AS_* 에셋명 직접 추출
_BP_GA_NAME_PAT  = re.compile(rb'\bGA_[A-Za-z0-9_]{1,60}\b')
_BP_GE_NAME_PAT  = re.compile(rb'\bGE_[A-Za-z0-9_]{1,60}\b')
_BP_AS_NAME_PAT  = re.compile(rb'\bAS_[A-Za-z0-9_]{1,60}\b')


# ── Data Models ───────────────────────────────────────────────

@dataclass
class GASClass:
    name:        str
    kind:        str          # "Ability", "Effect", "AttributeSet", "Component"
    source_file: str
    bases:       list[str]    = field(default_factory=list)
    tags:        list[str]    = field(default_factory=list)   # GameplayTags used
    ga_refs:     list[str]    = field(default_factory=list)   # TSubclassOf<UGA>
    ge_refs:     list[str]    = field(default_factory=list)   # TSubclassOf<UGE>
    asc_used:    bool         = False


@dataclass
class GASAssetRef:
    """A .uasset that references GAS classes."""
    asset_path:      str
    asset_name:      str         = ""                            # file stem e.g. "GA_BasicAttack"
    asset_role:      str         = "ref"                         # "GA"|"GE"|"AS"|"ABP"|"ref"
    class_refs:      list[str]   = field(default_factory=list)   # C++ class names found
    tags:            list[str]   = field(default_factory=list)   # GameplayTag strings found (high + low mixed, high first)
    tags_high:       list[str]   = field(default_factory=list)   # Known-prefix tags (high confidence)
    tags_low:        list[str]   = field(default_factory=list)   # Heuristic-only tags (low confidence)
    tag_confidence:  str         = "none"                        # "high" | "low" | "mixed" | "none"
    bp_ga_refs:      list[str]   = field(default_factory=list)   # Blueprint GA_ asset names referenced
    bp_ge_refs:      list[str]   = field(default_factory=list)   # Blueprint GE_ asset names referenced
    bp_as_refs:      list[str]   = field(default_factory=list)   # Blueprint AS_ asset names referenced
    has_ga:          bool        = False
    has_ge:          bool        = False
    has_as:          bool        = False
    has_abp:         bool        = False


@dataclass
class GASReport:
    project_path: str
    abilities:    list[GASClass]  = field(default_factory=list)
    effects:      list[GASClass]  = field(default_factory=list)
    attr_sets:    list[GASClass]  = field(default_factory=list)
    asc_classes:  list[str]       = field(default_factory=list)
    all_tags:     set[str]        = field(default_factory=set)   # high-confidence only
    all_tags_low: set[str]        = field(default_factory=set)   # low-confidence (noise-prone)
    asset_refs:   list[GASAssetRef] = field(default_factory=list)
    meta:         object          = field(default=None)   # AnalysisMetadata (lazy import)


# ── C++ Source Scanner ────────────────────────────────────────

def _is_likely_tag(s: str) -> bool:
    """Heuristic: GameplayTag strings are dot-separated, e.g. 'Ability.Attack.Melee'.

    강화된 필터:
    - 최소 3자 세그먼트 (2자 이하 거부: Nk, jO, HS, aK 등)
    - GUID/해시 세그먼트 거부 (e.g. BA8A81, 54FD...)
    - 숫자 비율 30% 초과 거부 (W16q = 50% digits)
    - 세그먼트 첫 글자 대문자 필수 (UE GameplayTag CamelCase 컨벤션)
    - 특수문자 포함 세그먼트 거부
    """
    parts = s.split(".")
    if len(parts) < 2 or len(s) >= 80:
        return False
    for p in parts:
        if len(p) < 3:                               # 2자 이하 세그먼트 거부
            return False
        if _GUID_SEG_PAT.match(p):                   # GUID/해시 세그먼트 거부
            return False
        digit_count = sum(1 for c in p if c.isdigit())
        if digit_count / len(p) > 0.30:             # 숫자 비율 30% 초과 거부
            return False
        if not p[0].isupper():                       # 첫 글자 대문자 필수
            return False
        if not re.match(r'^[A-Za-z][A-Za-z0-9_]*$', p):  # 특수문자 거부
            return False
    return True


def _tag_confidence(s: str) -> str:
    """Known prefix면 'high', 아니면 'low'."""
    for prefix in _KNOWN_TAG_PREFIXES:
        if s.startswith(prefix):
            return "high"
    return "low"


def _scan_cpp_for_request_tags(source_path: Path) -> set[str]:
    """Scan .cpp and .h files for RequestGameplayTag(TEXT("...")) string literals."""
    found: set[str] = set()
    for f in source_path.rglob("*.[ch]pp"):
        if any(p in _IGNORE_DIRS for p in f.parts):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for m in _REQUEST_TAG_PAT.finditer(text):
            tag = m.group(1)
            if _is_likely_tag(tag):
                found.add(tag)
    return found


def _scan_cpp_file(h_path: Path,
                   forced_kind: str | None = None,
                   forced_name: str | None = None) -> GASClass | None:
    """Scan a single .h file for GAS class declarations.

    forced_kind / forced_name: used in Pass 2 for indirect subclasses whose
    GAS kind was resolved via ancestor-walking rather than direct pattern match.
    """
    try:
        text = h_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    _kind_match = None
    if forced_kind is not None:
        kind = forced_kind
    else:
        kind = None
        ga_m = _GA_BASE_PAT.search(text)
        ge_m = _GE_BASE_PAT.search(text)
        as_m = _AS_BASE_PAT.search(text)
        if ga_m:
            kind = "Ability";     _kind_match = ga_m
        elif ge_m:
            kind = "Effect";      _kind_match = ge_m
        elif as_m:
            kind = "AttributeSet"; _kind_match = as_m
        elif _ASC_USE_PAT.search(text):
            kind = "Component"

    if kind is None:
        return None

    if forced_name is not None:
        class_name = forced_name
    else:
        # Extract class name from the GAS-matching line to avoid misidentifying
        # the first class in the file (e.g. an enum class declared above the GAS class).
        search_text = _kind_match.group(0) if _kind_match else text
        enum_names = {m.group(1) for m in _ENUM_CLS_PAT.finditer(text)}
        cls_m = None
        for m in re.finditer(r'\bclass\s+(?:\w+_API\s+)?(\w+)\s*:', search_text):
            if m.group(1) not in enum_names:
                cls_m = m
                break
        if not cls_m:
            return None
        class_name = cls_m.group(1)

    gas = GASClass(name=class_name, kind=kind, source_file=str(h_path))
    gas.asc_used = bool(_ASC_USE_PAT.search(text))

    # Tags
    for tag_m in _TAG_DECL_PAT.finditer(text):
        gas.tags.append(tag_m.group(1))
    for tag_m in _TAG_MACRO_PAT.finditer(text):
        gas.tags.append(tag_m.group(1))

    # GE references (TSubclassOf<UGameplayEffect>)
    for m in _UPROP_GE_PAT.finditer(text):
        gas.ge_refs.append(m.group(2))

    # GA references
    for m in _UPROP_GA_PAT.finditer(text):
        gas.ga_refs.append(m.group(2))

    return gas


# ── Asset Binary Scanner ──────────────────────────────────────

# _scan_uasset sentinel returns
_SKIP_LFS = "lfs"   # Git LFS stub — binary content unavailable
_SKIP_ERR = "err"   # File read error

_KNOWN_TAG_PREFIXES = (
    "Ability.", "Effect.", "Attribute.", "Status.", "Event.",
    "Gameplay.", "Tag.", "GAS.", "Input.", "GameplayCue.",
)
_IGNORE_DIRS = {"__ExternalActors__", "__ExternalObjects__", "Collections"}

# GUID/해시 세그먼트 거부 패턴 (예: BA8A81, 54FD 등)
_GUID_SEG_PAT = re.compile(r'^[0-9A-Fa-f]{6,}$')


def _scan_uasset(asset_path: Path, module_name: str):
    """Scan a single .uasset for GAS references.

    Returns:
      GASAssetRef  — GAS-relevant asset found
      None         — successfully read, no GAS content
      _SKIP_LFS    — Git LFS stub (binary content unavailable)
      _SKIP_ERR    — file read error
    """
    try:
        data = asset_path.read_bytes()
    except Exception:
        return _SKIP_ERR

    # Git LFS stub: small text file beginning with LFS version header
    if len(data) < 300 and data.lstrip().startswith(b'version https://git-lfs'):
        return _SKIP_LFS

    has_ga  = bool(_GA_BIN_PAT.search(data))
    has_ge  = bool(_GE_BIN_PAT.search(data))
    has_as  = bool(_AS_BIN_PAT.search(data))
    has_abp = bool(_ABP_BIN_PAT.search(data))

    if not (has_ga or has_ge or has_as or has_abp):
        return None

    # Determine asset role: IS-A (에셋 자체가 GAS 타입) vs ref (다른 에셋을 참조)
    # Supports both GA_* and BP_GA_* naming conventions
    stem = asset_path.stem
    _s = stem.upper()
    if _s.startswith("GA_") or _s.startswith("BP_GA_"):
        _role = "GA"
    elif _s.startswith("GE_") or _s.startswith("BP_GE_"):
        _role = "GE"
    elif _s.startswith("AS_") or _s.startswith("BP_AS_"):
        _role = "AS"
    elif _s.startswith("ABP_"):
        _role = "ABP"
    else:
        _role = "ref"

    ref = GASAssetRef(
        asset_path=str(asset_path),
        asset_name=stem,
        asset_role=_role,
        has_ga=has_ga, has_ge=has_ge, has_as=has_as, has_abp=has_abp
    )

    # Extract C++ class refs
    module_bytes = module_name.encode("ascii")
    for m in _MODULE_CLS_PAT.finditer(data):
        if m.group(1) == module_bytes:
            cls = m.group(2).decode("ascii", errors="ignore")
            if cls and not cls.endswith("_C"):
                ref.class_refs.append(cls)

    # Extract Blueprint asset names referenced (GA_*/GE_*/AS_* 에셋명 직접 추출)
    self_name = asset_path.stem
    for m in _BP_GA_NAME_PAT.finditer(data):
        name = m.group(0).decode("ascii", errors="ignore")
        if name != self_name:  # 자기 자신 제외
            ref.bp_ga_refs.append(name)
    for m in _BP_GE_NAME_PAT.finditer(data):
        name = m.group(0).decode("ascii", errors="ignore")
        if name != self_name:
            ref.bp_ge_refs.append(name)
    for m in _BP_AS_NAME_PAT.finditer(data):
        name = m.group(0).decode("ascii", errors="ignore")
        if name != self_name:
            ref.bp_as_refs.append(name)
    ref.bp_ga_refs = list(set(ref.bp_ga_refs))
    ref.bp_ge_refs = list(set(ref.bp_ge_refs))
    ref.bp_as_refs = list(set(ref.bp_as_refs))

    # Extract likely GameplayTag strings — high/low 신뢰도 분리 수집
    _seen_high: set[str] = set()
    _seen_low:  set[str] = set()
    for m in _TAG_STRING_PAT.finditer(data):
        s = m.group(1).decode("ascii", errors="ignore")
        if not _is_likely_tag(s):
            continue
        if _tag_confidence(s) == "high":
            _seen_high.add(s)
        else:
            _seen_low.add(s)

    # high 최대 25개, low 최대 5개 (노이즈 억제)
    ref.tags_high = sorted(_seen_high)[:25]
    ref.tags_low  = sorted(_seen_low)[:5]
    ref.tags      = ref.tags_high + ref.tags_low   # high 우선 병합

    if ref.tags_high and ref.tags_low:
        ref.tag_confidence = "mixed"
    elif ref.tags_high:
        ref.tag_confidence = "high"
    elif ref.tags_low:
        ref.tag_confidence = "low"
    else:
        ref.tag_confidence = "none"

    return ref


# ── Project Scanner ───────────────────────────────────────────

def _find_source_root(project_path: str) -> tuple[Path | None, Path | None]:
    """Return (source_root, content_root) for a UE5 project."""
    p = Path(project_path).resolve()
    source_root = content_root = None

    for candidate in [p] + list(p.parents):
        if (candidate / "Source").is_dir():
            source_root = candidate / "Source"
        if (candidate / "Content").is_dir():
            content_root = candidate / "Content"
        if source_root and content_root:
            break
        if source_root:
            break

    return source_root, content_root


def _detect_module(project_path: str) -> str:
    p = Path(project_path).resolve()
    for parent in [p] + list(p.parents):
        uprojects = list(parent.glob("*.uproject"))
        if uprojects:
            return uprojects[0].stem
    for part in reversed(p.parts):
        if part not in ("Source", "Content", ""):
            return part
    return "Game"


def _build_gas_report_raw(project_path: str,
                           class_name: str | None = None) -> GASReport:
    """Full scan — no cache. Called by analyze_gas and _cached_gas_report."""
    from .confidence import AnalysisMetadata, ConfidenceTier
    from .detector import _read_unreal_version

    source_root, content_root = _find_source_root(project_path)
    module_name = _detect_module(project_path)
    report = GASReport(project_path=project_path)

    meta = AnalysisMetadata(
        source_method="cpp_source_regex + binary_pattern_match",
        confidence=ConfidenceTier.MEDIUM,
    )
    ue_ver = _read_unreal_version(Path(project_path).resolve())
    if ue_ver:
        meta.ue_version = ue_ver
    report.meta = meta

    from .ue5_blueprint_refs import collect_content_roots
    all_content_roots = collect_content_roots(project_path)

    source_roots: list[tuple[object, str]] = []
    if source_root and source_root.exists():
        source_roots.append((source_root, "Project"))
    proj_root = source_root.parent if source_root else None
    if proj_root and (proj_root / "Plugins").is_dir():
        for plugin_dir in sorted((proj_root / "Plugins").iterdir()):
            if not plugin_dir.is_dir():
                continue
            plugin_src = plugin_dir / "Source"
            if plugin_src.is_dir():
                source_roots.append((plugin_src, f"Plugin/{plugin_dir.name}"))
            for sub in sorted(plugin_dir.iterdir()):
                if sub.is_dir() and (sub / "Source").is_dir():
                    source_roots.append((sub / "Source",
                                         f"Plugin/{plugin_dir.name}/{sub.name}"))

    # Pass 1: direct GAS detection + build parent_map/file_map for transitive lookup
    parent_map: dict[str, str]              = {}   # child → direct parent class name
    file_map:   dict[str, tuple[Path, str]] = {}   # child → (h_path, src_label)
    detected_names: set[str]                = set()

    for src_path, src_label in source_roots:
        for h_file in src_path.rglob("*.h"):
            # Build parent_map and file_map from ALL class declarations in this file
            try:
                h_text = h_file.read_text(encoding="utf-8", errors="replace")
                for m in _CLS_DECL_PAT.finditer(h_text):
                    child, parent = m.group(1), m.group(2)
                    parent_map[child] = parent
                    file_map[child]   = (h_file, src_label)
            except Exception:
                pass

            # Direct GAS scan (unchanged)
            gas_cls = _scan_cpp_file(h_file)
            if gas_cls is None:
                continue
            if class_name and gas_cls.name.lower() != class_name.lower():
                continue
            detected_names.add(gas_cls.name)
            gas_cls.source_file = f"[{src_label}] {gas_cls.source_file}"
            if gas_cls.kind == "Ability":
                report.abilities.append(gas_cls)
            elif gas_cls.kind == "Effect":
                report.effects.append(gas_cls)
            elif gas_cls.kind == "AttributeSet":
                report.attr_sets.append(gas_cls)
            elif gas_cls.kind == "Component" and gas_cls.name not in report.asc_classes:
                report.asc_classes.append(gas_cls.name)

        # Scan .cpp files for RequestGameplayTag(TEXT("...")) literals
        report.all_tags.update(_scan_cpp_for_request_tags(src_path))

    # Pass 2: transitive inheritance — find indirect GAS subclasses missed by Pass 1
    def _resolve_gas_kind(child: str, depth: int = 0) -> str | None:
        """Walk parent_map ancestors until a GAS root is found (or depth exceeded)."""
        if depth > 20:
            return None
        parent = parent_map.get(child)
        if parent is None:
            return None
        if parent in _GAS_ROOT_KIND:
            return _GAS_ROOT_KIND[parent]
        return _resolve_gas_kind(parent, depth + 1)

    for child_name, (h_file, src_label) in file_map.items():
        if child_name in detected_names:
            continue
        kind = _resolve_gas_kind(child_name)
        if kind is None:
            continue
        if class_name and child_name.lower() != class_name.lower():
            continue
        gas_cls = _scan_cpp_file(h_file, forced_kind=kind, forced_name=child_name)
        if gas_cls is None:
            continue
        detected_names.add(child_name)
        gas_cls.source_file = f"[{src_label}] {gas_cls.source_file}"
        if gas_cls.kind == "Ability":
            report.abilities.append(gas_cls)
        elif gas_cls.kind == "Effect":
            report.effects.append(gas_cls)
        elif gas_cls.kind == "AttributeSet":
            report.attr_sets.append(gas_cls)

    import os as _os
    for content_dir, _lbl in all_content_roots:
        if not content_dir.exists():
            continue
        for root, dirs, files in _os.walk(content_dir):
            dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
            for fname in files:
                if not fname.endswith((".uasset", ".umap")):
                    continue
                meta.scanned += 1
                result = _scan_uasset(Path(root) / fname, module_name)
                if result is _SKIP_LFS:
                    meta.skipped_lfs += 1
                elif result is _SKIP_ERR:
                    meta.skipped_error += 1
                else:
                    meta.parsed += 1
                    if result is not None:
                        report.asset_refs.append(result)
                        report.all_tags.update(result.tags_high)
                        report.all_tags_low.update(result.tags_low)

    # Improvement 2: C++ 소스에서 클래스를 찾은 경우 HIGH 신뢰도로 상향
    if report.abilities or report.effects or report.attr_sets:
        meta.confidence = ConfidenceTier.HIGH
        meta.source_method = "cpp_source_regex"
        if meta.parsed > 0:
            meta.source_method += " + binary_pattern_match"

    _resolve_asset_roles(report)
    return report


def _resolve_asset_roles(report: GASReport) -> None:
    """C++ 스캔 결과와 .uasset class_refs를 교차 검증하여 IS-A 역할을 결정한다.

    우선순위:
      1. Cross-reference: class_refs에 알려진 GAS C++ 클래스가 있으면 → 해당 role
      2. Fallback: _scan_uasset에서 설정한 명명 규칙 기반 role 유지

    한계:
      - C++ 중간 클래스 없이 순수 Blueprint로만 만든 GAS 에셋은
        명명 규칙 fallback에 의존 (cross-ref 불가)

    TODO: UE Editor 통합 확장 계획
      - 에디터 실행 중이거나 설치 경로(UE.exe)에 접근 가능한 경우
        에디터 Python API(unreal.EditorAssetLibrary 등)로 완전한 SuperClass 파싱 수행
      - 그 경우 본 함수 대신 에디터 쿼리 결과를 사용하도록 교체 예정
    """
    # C++ 스캔 결과로 역할 lookup 테이블 구성 (U 접두사 유무 모두 등록)
    role_lookup: dict[str, str] = {}
    for ga in report.abilities:
        role_lookup[ga.name] = "GA"
        if ga.name.startswith("U"):
            role_lookup[ga.name[1:]] = "GA"
    for ge in report.effects:
        role_lookup[ge.name] = "GE"
        if ge.name.startswith("U"):
            role_lookup[ge.name[1:]] = "GE"
    for aset in report.attr_sets:
        role_lookup[aset.name] = "AS"
        if aset.name.startswith("U"):
            role_lookup[aset.name[1:]] = "AS"

    for ref in report.asset_refs:
        for cls in ref.class_refs:
            if cls in role_lookup:
                ref.asset_role = role_lookup[cls]
                break


def _gas_report_to_dict(r: GASReport) -> dict:
    import dataclasses
    # meta는 dataclasses.asdict에서 제외 후 별도 직렬화
    meta_obj = r.meta
    r.meta = None
    d = dataclasses.asdict(r)
    r.meta = meta_obj
    d["all_tags"]     = list(r.all_tags)      # set → list for JSON
    d["all_tags_low"] = list(r.all_tags_low)  # set → list for JSON
    if meta_obj is not None:
        import dataclasses as _dc
        dm = _dc.asdict(meta_obj)
        dm["confidence"] = meta_obj.confidence.value  # Enum → str
        d["meta"] = dm
    return d


def _gas_report_from_dict(d: dict) -> GASReport:
    from .confidence import AnalysisMetadata, ConfidenceTier
    def _cls(x): return GASClass(**{k: v for k, v in x.items()
                                    if k in GASClass.__dataclass_fields__})
    def _ref(x): return GASAssetRef(**{k: v for k, v in x.items()
                                       if k in GASAssetRef.__dataclass_fields__})
    meta = None
    if "meta" in d and d["meta"]:
        try:
            md = d["meta"]
            meta = AnalysisMetadata(
                source_method=md.get("source_method", ""),
                confidence=ConfidenceTier(md.get("confidence", "none")),
                scanned=md.get("scanned", 0),
                parsed=md.get("parsed", 0),
                skipped_lfs=md.get("skipped_lfs", 0),
                skipped_error=md.get("skipped_error", 0),
                ue_version=md.get("ue_version", ""),
            )
        except Exception:
            pass
    return GASReport(
        project_path=d["project_path"],
        abilities=[_cls(x) for x in d.get("abilities", [])],
        effects=[_cls(x) for x in d.get("effects", [])],
        attr_sets=[_cls(x) for x in d.get("attr_sets", [])],
        asc_classes=d.get("asc_classes", []),
        all_tags=set(d.get("all_tags", [])),
        all_tags_low=set(d.get("all_tags_low", [])),
        asset_refs=[_ref(x) for x in d.get("asset_refs", [])],
        meta=meta,
    )


def _cached_gas_report(project_path: str) -> GASReport:
    from .uasset_cache import fingerprint_combined, load_cache, save_cache
    from .ue5_blueprint_refs import collect_content_roots

    # Content roots (.uasset) + Source roots (.h/.cpp) 모두 감시
    content_roots = [r for r, _ in collect_content_roots(project_path)]
    source_root, _ = _find_source_root(project_path)
    source_roots: list[Path] = []
    if source_root and source_root.exists():
        source_roots.append(source_root)
    proj_root = source_root.parent if source_root else None
    if proj_root and (proj_root / "Plugins").is_dir():
        for plugin_dir in sorted((proj_root / "Plugins").iterdir()):
            if not plugin_dir.is_dir():
                continue
            if (plugin_dir / "Source").is_dir():
                source_roots.append(plugin_dir / "Source")
            for sub in plugin_dir.iterdir():
                if sub.is_dir() and (sub / "Source").is_dir():
                    source_roots.append(sub / "Source")

    # C++ 소스가 바뀌거나 uasset이 바뀌면 모두 무효화
    fp = fingerprint_combined(content_roots, source_roots)
    cache_key = "gas_scan"
    cached = load_cache(project_path, cache_key)
    if cached and cached.get("_fp") == fp:
        try:
            return _gas_report_from_dict(cached["data"])
        except Exception:
            pass
    report = _build_gas_report_raw(project_path)
    save_cache(project_path, cache_key,
               {"_fp": fp, "data": _gas_report_to_dict(report)})
    return report


def analyze_gas(project_path: str,
                class_name: str | None = None,
                detail_level: str = "summary",
                category: str | None = None,
                query: str | None = None) -> str:
    """
    Analyze GAS (Gameplay Ability System) usage in a UE5 project.

    Args:
        project_path: UE5 Source or project root path.
        class_name:   Optional class name filter (bypasses cache).
        detail_level: "summary" (default) shows counts + tag distribution.
                      "full" returns the complete report.
        category:     Tag prefix filter, e.g. "Event" → only Event.* tags
                      and abilities/effects referencing those tags.
        query:        Keyword search across class names, tag names, asset names
                      (case-insensitive).

    Returns:
        Formatted GAS analysis report.
    """
    if class_name is None:
        report = _cached_gas_report(project_path)
    else:
        report = _build_gas_report_raw(project_path, class_name)

    if category or query:
        return _format_gas_filtered(report, category, query)
    if detail_level == "summary":
        return _format_gas_summary(report)
    return _format_gas_report(report)


# ── Report Formatting ─────────────────────────────────────────

def _format_gas_summary(r: GASReport) -> str:
    """Return a compact summary with tag distribution only. ~500 tokens."""
    # Asset role breakdown
    _role_counts: dict[str, int] = {}
    for _ar in r.asset_refs:
        _role_counts[_ar.asset_role] = _role_counts.get(_ar.asset_role, 0) + 1

    lines = [
        "# GAS Analysis — Summary",
        f"Project: {r.project_path}",
        "",
    ]
    if r.meta:
        lines += [r.meta.to_header(), ""]
    lines += [
        "## Counts",
        f"- GameplayAbilities (C++):         {len(r.abilities)}",
        f"- GameplayEffects (C++):           {len(r.effects)}",
        f"- AttributeSets (C++):             {len(r.attr_sets)}",
        f"- Classes with ASC:               {len(r.asc_classes)}",
        f"- GameplayTags (in assets):        {len(r.all_tags)}",
        f"- GAS-related .uassets:           {len(r.asset_refs)}",
        "",
        "## Asset Roles",
        f"  IS-A GA  (GA_*):  {_role_counts.get('GA', 0)}",
        f"  IS-A GE  (GE_*):  {_role_counts.get('GE', 0)}",
        f"  IS-A AS  (AS_*):  {_role_counts.get('AS', 0)}",
        f"  IS-A ABP (ABP_*): {_role_counts.get('ABP', 0)}",
        f"  References only:  {_role_counts.get('ref', 0)}",
        "",
    ]

    if r.abilities:
        lines.append(f"## Abilities ({len(r.abilities)})")
        for ga in r.abilities[:10]:
            lines.append(f"  - {ga.name}")
        if len(r.abilities) > 10:
            lines.append(f"  ... and {len(r.abilities) - 10} more")
        lines.append("")

    if r.all_tags:
        by_prefix: dict[str, list[str]] = {}
        for tag in r.all_tags:
            prefix = tag.split(".")[0]
            by_prefix.setdefault(prefix, []).append(tag)
        lines.append(f"## Tag Distribution (by prefix)")
        for prefix, tags in sorted(by_prefix.items(), key=lambda x: -len(x[1])):
            lines.append(f"  {prefix}.*  ({len(tags)})")
        lines.append("")
        lines.append("💡 Use category=\"<Prefix>\" to filter by tag prefix, "
                     "query=\"<keyword>\" to search, or detail_level=\"full\" for complete report.")

    return "\n".join(lines)


def _format_gas_filtered(r: GASReport,
                          category: str | None,
                          query: str | None) -> str:
    """Return a filtered GASReport view. Filters applied at format time — cache unchanged."""
    q = query.lower() if query else None
    cat = category.lower() if category else None

    def _tag_matches(tag: str) -> bool:
        if cat and not tag.lower().startswith(cat + ".") and tag.lower() != cat:
            return False
        if q and q not in tag.lower():
            return False
        return True

    def _class_matches(name: str) -> bool:
        return not q or q in name.lower()

    def _asset_matches(ref: GASAssetRef) -> bool:
        if q and q not in ref.asset_name.lower():
            if not any(q in c.lower() for c in ref.class_refs):
                if not any(q in t.lower() for t in ref.tags):
                    return False
        return True

    # Filter tags
    matched_tags = sorted(t for t in r.all_tags if _tag_matches(t))

    # Filter abilities — keep if name matches OR any tag matches
    def _ga_matches(ga: GASClass) -> bool:
        if q and _class_matches(ga.name):
            return True
        if any(_tag_matches(t) for t in ga.tags):
            return True
        return not (q or cat)

    filtered_abilities = [ga for ga in r.abilities if _ga_matches(ga)]
    filtered_effects   = [ge for ge in r.effects if _class_matches(ge.name)] if q else r.effects
    filtered_assets    = [ref for ref in r.asset_refs if _asset_matches(ref)] if q else r.asset_refs

    label_parts = []
    if cat:
        label_parts.append(f'category="{category}"')
    if q:
        label_parts.append(f'query="{query}"')
    filter_label = ", ".join(label_parts)

    lines = [
        f"# GAS Analysis — Filtered ({filter_label})",
        f"Project: {r.project_path}",
        f"Matched: {len(matched_tags)} tags · {len(filtered_abilities)} abilities · {len(filtered_effects)} effects",
        "",
    ]

    if matched_tags:
        lines.append(f"## Matching Tags ({len(matched_tags)})")
        for t in matched_tags[:30]:
            lines.append(f"  - {t}")
        if len(matched_tags) > 30:
            lines.append(f"  ... and {len(matched_tags) - 30} more")
        lines.append("")

    if filtered_abilities:
        lines.append(f"## Matching Abilities ({len(filtered_abilities)})")
        for ga in filtered_abilities:
            lines.append(f"\n### {ga.name}")
            lines.append(f"  File: {Path(ga.source_file).name}")
            rel_tags = [t for t in ga.tags if _tag_matches(t)] if (cat or q) else ga.tags
            if rel_tags:
                lines.append(f"  Tags: {', '.join(rel_tags[:10])}")
            if ga.ge_refs:
                lines.append(f"  GE applied: {', '.join(ga.ge_refs[:5])}")

    if q and filtered_effects:
        lines.append(f"\n## Matching Effects ({len(filtered_effects)})")
        for ge in filtered_effects:
            lines.append(f"  - {ge.name}  ({Path(ge.source_file).name})")

    if q and filtered_assets:
        lines.append(f"\n## Matching Assets ({len(filtered_assets)})")
        for ref in filtered_assets[:20]:
            _badge = f"[{ref.asset_role}]" if ref.asset_role != "ref" else "[ref]"
            lines.append(f"  - {ref.asset_name}  {_badge}")

    if not matched_tags and not filtered_abilities and not (q and filtered_effects):
        lines.append("No matches found. Try a broader filter or detail_level=\"full\".")

    return "\n".join(lines)


def _format_gas_report(r: GASReport) -> str:
    _role_counts: dict[str, int] = {}
    for _ar in r.asset_refs:
        _role_counts[_ar.asset_role] = _role_counts.get(_ar.asset_role, 0) + 1

    lines = [
        "# GAS (Gameplay Ability System) Analysis",
        f"Project: {r.project_path}",
        "",
    ]
    if r.meta:
        lines += [r.meta.to_header(), ""]
    lines += [
        "## Summary",
        f"- Abilities (UGameplayAbility subclasses):  {len(r.abilities)}",
        f"- Effects  (UGameplayEffect subclasses):    {len(r.effects)}",
        f"- AttributeSets:                            {len(r.attr_sets)}",
        f"- Classes using AbilitySystemComponent:     {len(r.asc_classes)}",
        f"- GameplayTags found in assets:             {len(r.all_tags)}",
        f"- GAS-related .uassets:                     {len(r.asset_refs)}",
        f"    IS-A GA={_role_counts.get('GA',0)}  GE={_role_counts.get('GE',0)}"
        f"  AS={_role_counts.get('AS',0)}  ABP={_role_counts.get('ABP',0)}"
        f"  ref={_role_counts.get('ref',0)}",
        "",
    ]

    if r.abilities:
        lines.append(f"## GameplayAbilities ({len(r.abilities)})")
        for ga in r.abilities:
            lines.append(f"\n### {ga.name}")
            lines.append(f"  File: {Path(ga.source_file).name}")
            if ga.tags:
                lines.append(f"  Tags used: {', '.join(ga.tags[:10])}")
            if ga.ge_refs:
                lines.append(f"  GE applied: {', '.join(ga.ge_refs[:5])}")

    if r.effects:
        lines.append(f"\n## GameplayEffects ({len(r.effects)})")
        for ge in r.effects:
            lines.append(f"  - {ge.name}  ({Path(ge.source_file).name})")

    if r.attr_sets:
        lines.append(f"\n## AttributeSets ({len(r.attr_sets)})")
        for aset in r.attr_sets:
            lines.append(f"  - {aset.name}  ({Path(aset.source_file).name})")

    if r.asc_classes:
        lines.append("\n## Classes using AbilitySystemComponent")
        for cls in r.asc_classes[:20]:
            lines.append(f"  - {cls}")

    if r.all_tags:
        sorted_tags = sorted(r.all_tags)
        lines.append(f"\n## GameplayTags found in assets ({len(r.all_tags)})")
        # Group by top-level prefix
        by_prefix: dict[str, list[str]] = {}
        for tag in sorted_tags:
            prefix = tag.split(".")[0]
            by_prefix.setdefault(prefix, []).append(tag)
        for prefix, tags in sorted(by_prefix.items()):
            lines.append(f"  {prefix}.*  ({len(tags)} tags)")
            for t in tags[:5]:
                lines.append(f"    - {t}")
            if len(tags) > 5:
                lines.append(f"    ... and {len(tags)-5} more")

    return "\n".join(lines)


def build_gas_report(project_path: str) -> GASReport:
    """
    GASReport 객체를 직접 반환 (시각화/JSON API용).
    프로젝트 Source + Plugin Source / Content 전체 스캔.
    """
    from .confidence import AnalysisMetadata, ConfidenceTier
    from .detector import _read_unreal_version
    import os as _os

    from .ue5_blueprint_refs import collect_content_roots
    source_root, _ = _find_source_root(project_path)
    module_name = _detect_module(project_path)
    report = GASReport(project_path=project_path)

    meta = AnalysisMetadata(
        source_method="cpp_source_regex + binary_pattern_match",
        confidence=ConfidenceTier.MEDIUM,
    )
    ue_ver = _read_unreal_version(Path(project_path).resolve())
    if ue_ver:
        meta.ue_version = ue_ver
    report.meta = meta

    # ── Source 스캔 (프로젝트 + 플러그인) ────────────────────
    src_roots = []
    if source_root and source_root.exists():
        src_roots.append(source_root)
    proj_root = source_root.parent if source_root else None
    if proj_root and (proj_root / "Plugins").is_dir():
        for plugin_dir in sorted((proj_root / "Plugins").iterdir()):
            if not plugin_dir.is_dir():
                continue
            if (plugin_dir / "Source").is_dir():
                src_roots.append(plugin_dir / "Source")
            for sub in plugin_dir.iterdir():
                if sub.is_dir() and (sub / "Source").is_dir():
                    src_roots.append(sub / "Source")

    for src_path in src_roots:
        for h_file in src_path.rglob("*.h"):
            gas_cls = _scan_cpp_file(h_file)
            if gas_cls is None:
                continue
            if gas_cls.kind == "Ability":
                report.abilities.append(gas_cls)
            elif gas_cls.kind == "Effect":
                report.effects.append(gas_cls)
            elif gas_cls.kind == "AttributeSet":
                report.attr_sets.append(gas_cls)
            elif gas_cls.kind == "Component" and gas_cls.name not in report.asc_classes:
                report.asc_classes.append(gas_cls.name)

    # ── Content 스캔 (프로젝트 + 플러그인) ───────────────────
    for content_dir, _lbl in collect_content_roots(project_path):
        if not content_dir.exists():
            continue
        for root, dirs, files in _os.walk(content_dir):
            dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
            for fname in files:
                if not fname.endswith((".uasset", ".umap")):
                    continue
                meta.scanned += 1
                result = _scan_uasset(Path(root) / fname, module_name)
                if result is _SKIP_LFS:
                    meta.skipped_lfs += 1
                elif result is _SKIP_ERR:
                    meta.skipped_error += 1
                else:
                    meta.parsed += 1
                    if result is not None:
                        report.asset_refs.append(result)
                        report.all_tags.update(result.tags_high)
                        report.all_tags_low.update(result.tags_low)

    _resolve_asset_roles(report)
    return report
