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
_TAG_DECL_PAT  = re.compile(r'FGameplayTag(?:Container)?\s+(\w+)')
_TAG_MACRO_PAT = re.compile(r'GAMEPLAYTAG_DECLARE_TAG\s*\(\s*(\w+(?:\.\w+)*)\s*\)')

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
    asset_path:   str
    asset_name:   str         = ""                            # file stem e.g. "GA_BasicAttack"
    class_refs:   list[str]   = field(default_factory=list)   # C++ class names found
    tags:         list[str]   = field(default_factory=list)   # GameplayTag strings found
    bp_ga_refs:   list[str]   = field(default_factory=list)   # Blueprint GA_ asset names referenced
    bp_ge_refs:   list[str]   = field(default_factory=list)   # Blueprint GE_ asset names referenced
    bp_as_refs:   list[str]   = field(default_factory=list)   # Blueprint AS_ asset names referenced
    has_ga:       bool        = False
    has_ge:       bool        = False
    has_as:       bool        = False
    has_abp:      bool        = False


@dataclass
class GASReport:
    project_path: str
    abilities:    list[GASClass]  = field(default_factory=list)
    effects:      list[GASClass]  = field(default_factory=list)
    attr_sets:    list[GASClass]  = field(default_factory=list)
    asc_classes:  list[str]       = field(default_factory=list)
    all_tags:     set[str]        = field(default_factory=set)
    asset_refs:   list[GASAssetRef] = field(default_factory=list)


# ── C++ Source Scanner ────────────────────────────────────────

def _is_likely_tag(s: str) -> bool:
    """Heuristic: GameplayTag strings are dot-separated, e.g. 'Ability.Attack.Melee'."""
    parts = s.split(".")
    return (len(parts) >= 2 and
            all(p[0].isupper() or p[0].isalpha() for p in parts) and
            len(s) < 80)


def _scan_cpp_file(h_path: Path) -> GASClass | None:
    """Scan a single .h file for GAS class declarations."""
    try:
        text = h_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None

    kind: str | None = None
    if _GA_BASE_PAT.search(text):  kind = "Ability"
    elif _GE_BASE_PAT.search(text): kind = "Effect"
    elif _AS_BASE_PAT.search(text): kind = "AttributeSet"
    elif _ASC_USE_PAT.search(text): kind = "Component"

    if kind is None:
        return None

    # Extract class name — handle optional MODULE_API macro
    # Patterns: "class MYMODULE_API UMyClass : public" or "class UMyClass : public"
    cls_m = re.search(r'\bclass\s+(?:\w+_API\s+)?(\w+)\s*:', text)
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

_KNOWN_TAG_PREFIXES = (
    "Ability.", "Effect.", "Attribute.", "Status.", "Event.",
    "Gameplay.", "Tag.", "GAS.", "Input.", "GameplayCue.",
)
_IGNORE_DIRS = {"__ExternalActors__", "__ExternalObjects__", "Collections"}


def _scan_uasset(asset_path: Path, module_name: str) -> GASAssetRef | None:
    """Scan a single .uasset for GAS references."""
    try:
        data = asset_path.read_bytes()
    except Exception:
        return None

    has_ga  = bool(_GA_BIN_PAT.search(data))
    has_ge  = bool(_GE_BIN_PAT.search(data))
    has_as  = bool(_AS_BIN_PAT.search(data))
    has_abp = bool(_ABP_BIN_PAT.search(data))

    if not (has_ga or has_ge or has_as or has_abp):
        return None

    ref = GASAssetRef(
        asset_path=str(asset_path),
        asset_name=asset_path.stem,
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

    # Extract likely GameplayTag strings
    for m in _TAG_STRING_PAT.finditer(data):
        s = m.group(1).decode("ascii", errors="ignore")
        if _is_likely_tag(s):
            ref.tags.append(s)

    ref.tags = list(set(ref.tags))[:30]  # dedup + cap
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
    source_root, content_root = _find_source_root(project_path)
    module_name = _detect_module(project_path)
    report = GASReport(project_path=project_path)

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

    for src_path, src_label in source_roots:
        for h_file in src_path.rglob("*.h"):
            gas_cls = _scan_cpp_file(h_file)
            if gas_cls is None:
                continue
            if class_name and gas_cls.name.lower() != class_name.lower():
                continue
            gas_cls.source_file = f"[{src_label}] {gas_cls.source_file}"
            if gas_cls.kind == "Ability":
                report.abilities.append(gas_cls)
            elif gas_cls.kind == "Effect":
                report.effects.append(gas_cls)
            elif gas_cls.kind == "AttributeSet":
                report.attr_sets.append(gas_cls)
            elif gas_cls.kind == "Component" and gas_cls.name not in report.asc_classes:
                report.asc_classes.append(gas_cls.name)

    import os as _os
    for content_dir, _lbl in all_content_roots:
        if not content_dir.exists():
            continue
        for root, dirs, files in _os.walk(content_dir):
            dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
            for fname in files:
                if not fname.endswith((".uasset", ".umap")):
                    continue
                asset_ref = _scan_uasset(Path(root) / fname, module_name)
                if asset_ref:
                    report.asset_refs.append(asset_ref)
                    report.all_tags.update(asset_ref.tags)

    return report


def _gas_report_to_dict(r: GASReport) -> dict:
    import dataclasses
    d = dataclasses.asdict(r)
    d["all_tags"] = list(r.all_tags)   # set → list for JSON
    return d


def _gas_report_from_dict(d: dict) -> GASReport:
    def _cls(x): return GASClass(**{k: v for k, v in x.items()
                                    if k in GASClass.__dataclass_fields__})
    def _ref(x): return GASAssetRef(**{k: v for k, v in x.items()
                                       if k in GASAssetRef.__dataclass_fields__})
    return GASReport(
        project_path=d["project_path"],
        abilities=[_cls(x) for x in d.get("abilities", [])],
        effects=[_cls(x) for x in d.get("effects", [])],
        attr_sets=[_cls(x) for x in d.get("attr_sets", [])],
        asc_classes=d.get("asc_classes", []),
        all_tags=set(d.get("all_tags", [])),
        asset_refs=[_ref(x) for x in d.get("asset_refs", [])],
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
                class_name: str | None = None) -> str:
    """
    Analyze GAS (Gameplay Ability System) usage in a UE5 project.

    Args:
        project_path: UE5 Source or project root path.
        class_name:   Optional class name filter (bypasses cache).

    Returns:
        Formatted GAS analysis report.
    """
    if class_name is None:
        report = _cached_gas_report(project_path)
    else:
        report = _build_gas_report_raw(project_path, class_name)
    return _format_gas_report(report)


# ── Report Formatting ─────────────────────────────────────────

def _format_gas_report(r: GASReport) -> str:
    lines = [
        "# GAS (Gameplay Ability System) Analysis",
        f"Project: {r.project_path}",
        "",
        "## Summary",
        f"- Abilities (UGameplayAbility subclasses):  {len(r.abilities)}",
        f"- Effects  (UGameplayEffect subclasses):    {len(r.effects)}",
        f"- AttributeSets:                            {len(r.attr_sets)}",
        f"- Classes using AbilitySystemComponent:     {len(r.asc_classes)}",
        f"- GameplayTags found in assets:             {len(r.all_tags)}",
        f"- GAS-related .uassets:                     {len(r.asset_refs)}",
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
    import os as _os

    from .ue5_blueprint_refs import collect_content_roots
    source_root, _ = _find_source_root(project_path)
    module_name = _detect_module(project_path)
    report = GASReport(project_path=project_path)

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
                asset_ref = _scan_uasset(Path(root) / fname, module_name)
                if asset_ref:
                    report.asset_refs.append(asset_ref)
                    report.all_tags.update(asset_ref.tags)

    return report
