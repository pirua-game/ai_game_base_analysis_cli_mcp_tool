"""
gdep-mcp/server.py

gdep MCP Server — Game Engine Dependency & AI Analysis
FastMCP 기반. Claude Desktop / Cursor / Continue.dev에서 즉시 사용 가능.

실행 방법:
    cd gdep-cli
    pip install -e .
    pip install mcp[cli]
    python -m gdep_mcp.server
    # 또는
    mcp run gdep-mcp/server.py

Claude Desktop 설정 (~/.config/claude/config.json):
    {
      "mcpServers": {
        "gdep": {
          "command": "python",
          "args": ["-m", "gdep_mcp.server"],
          "cwd": "/path/to/gdep/gdep-cli"
        }
      }
    }
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# ── 경로 설정 ──────────────────────────────────────────────────
# gdep-mcp/server.py → gdep-cli/ 가 sys.path에 있어야 gdep 패키지를 import할 수 있음
_HERE      = Path(__file__).parent          # gdep-cli/gdep-mcp/
_GDEP_ROOT = _HERE.parent                   # gdep-cli/
if str(_GDEP_ROOT) not in sys.path:
    sys.path.insert(0, str(_GDEP_ROOT))

from mcp.server.fastmcp import FastMCP
from gdep_mcp.tools.analyze_impact_and_risk import run as _impact_run
from gdep_mcp.tools.explore_class_semantics import run as _semantics_run
from gdep_mcp.tools.inspect_architectural_health import run as _health_run
from gdep_mcp.tools.trace_gameplay_flow import run as _flow_run
from gdep_mcp.tools.suggest_test_scope import run as _test_scope_run
from gdep_mcp.tools.suggest_lint_fixes import run as _lint_fixes_run
from gdep_mcp.tools.summarize_project_diff import run as _diff_summary_run
from gdep_mcp.tools.analyze_axmol_events import run as _axmol_events_run
from gdep_mcp.tools.explain_method_logic import run as _explain_logic_run

# ── 추가 분석 모듈 (3~7단계 기능) — 로드 실패해도 서버는 기동됨 ──
try:
    from gdep.unity_event_refs import build_event_map, format_event_result
    _UNITY_EVENTS_AVAILABLE = True
except ImportError:
    _UNITY_EVENTS_AVAILABLE = False

try:
    from gdep.unity_animator import analyze_animator
    _UNITY_ANIMATOR_AVAILABLE = True
except ImportError:
    _UNITY_ANIMATOR_AVAILABLE = False

try:
    from gdep.ue5_gas_analyzer import analyze_gas
    _UE5_GAS_AVAILABLE = True
except ImportError:
    _UE5_GAS_AVAILABLE = False

try:
    from gdep.ue5_ai_analyzer import analyze_behavior_tree, analyze_state_tree
    _UE5_AI_AVAILABLE = True
except ImportError:
    _UE5_AI_AVAILABLE = False

try:
    from gdep.ue5_animator import analyze_abp, analyze_montage
    _UE5_ANIMATOR_AVAILABLE = True
except ImportError:
    _UE5_ANIMATOR_AVAILABLE = False

try:
    from gdep.ue5_blueprint_mapping import (
        build_bp_map,
        format_full_project_map,
        format_mapping,
    )
    _UE5_BP_MAPPING_AVAILABLE = True
except ImportError:
    _UE5_BP_MAPPING_AVAILABLE = False

# ── MCP 서버 초기화 ────────────────────────────────────────────
mcp = FastMCP("gdep")


# ════════════════════════════════════════════════════════════════
# CONTEXT TOOL — 항상 먼저 호출 권장
# ════════════════════════════════════════════════════════════════

@mcp.tool()
def get_project_context(project_path: str) -> str:
    """
    Get a complete AI-ready overview of the game project. CALL THIS FIRST.

    Returns project type, source path, class count, high-coupling classes,
    GAS summary (UE5), Animator controllers (Unity), and a decision guide
    for which gdep tool to use for each type of question.

    If .gdep/AGENTS.md exists in the project root (created by 'gdep init'),
    returns its content. Otherwise generates context on the fly.

    Use this tool at the start of any coding session on a game project to
    understand the codebase structure before diving into specific tasks.

    Args:
        project_path: Any path within the game project (root, Source, or Assets).
    """
    try:
        from gdep.init_context import build_context_output
        return build_context_output(project_path)
    except Exception as e:
        return f"[get_project_context] Error: {e}"

@mcp.tool()
def analyze_impact_and_risk(project_path: str, class_name: str,
                             detail_level: str = "summary",
                             query: str | None = None) -> str:
    """
    Analyze the blast radius and risks before modifying a class.

    ⚠️ CRITICAL: Always call with detail_level="summary" first.
    Only use detail_level="full" if the user explicitly asks for the complete impact tree.
    Use query= to narrow results before escalating to "full".

    USE THIS TOOL WHEN:
    - User says "I want to refactor / modify / rename / delete class X"
    - User asks "what will break if I change X?"
    - User asks "is it safe to modify X?"
    - Before any non-trivial code change to understand side effects

    Returns:
    - Reverse dependency tree: all classes that directly or indirectly use X
    - Unity prefab / UE5 blueprint assets that reference X
    - Lint issues already present in or around X (anti-patterns to fix)

    Args:
        project_path: Absolute path to Scripts (Unity) or Source (UE5) folder.
        class_name:   Class to analyze. E.g. "BattleManager", "APlayerCharacter"
        detail_level: "summary" (default) — affected class count + top-5 risk items (fast).
                      "full"    — complete impact tree + all lint issues (expensive, use sparingly).
        query:        Optional filter string — only results containing this
                      class name or pattern are included. E.g. "Battle", "Manager"
    """
    return _impact_run(project_path, class_name, detail_level, query)


@mcp.tool()
def trace_gameplay_flow(project_path: str, class_name: str, method_name: str,
                        depth: int = 4, include_source: bool = True) -> str:
    """
    Trace a method's full call chain and show relevant source code.

    USE THIS TOOL WHEN:
    - User asks "how does feature X work?"
    - User asks "trace the flow of method Y"
    - User is debugging and wants to see the execution path
    - User asks "what happens when Z is called?"
    - User wants to understand async chains, locks, or event dispatches

    Returns:
    - Call tree from CLASS.METHOD with async/lock/dispatch annotations
    - Source code of the entry-point class for immediate reference

    Args:
        project_path:   Absolute path to Scripts/Source folder.
        class_name:     Entry-point class. E.g. "ManagerBattle", "AHSCharacterBase"
        method_name:    Entry-point method. E.g. "PlayHand", "BeginPlay", "ActivateAbility"
        depth:          Tracing depth (default 4, max recommended 6).
        include_source: Append source code of entry class (default True).
    """
    return _flow_run(project_path, class_name, method_name, depth, include_source)


@mcp.tool()
def inspect_architectural_health(project_path: str, include_dead_code: bool = True,
                                  include_refs: bool = True, top: int = 15) -> str:
    """
    Full architectural health check: coupling, cycles, dead code, and anti-patterns.

    USE THIS TOOL WHEN:
    - User asks "is the codebase in good shape?"
    - User asks "what's the technical debt here?"
    - User asks "are there circular dependencies?"
    - User asks "what code is dead / unused?"
    - At the start of a refactoring session for an overview

    Note: May take 10-60 seconds on large projects (>500 files).

    Args:
        project_path:      Absolute path to Scripts/Source folder.
        include_dead_code: Detect unreferenced classes (default True).
        include_refs:      Factor in engine asset refs for dead-code filtering (default True).
        top:               Number of high-coupling classes to show (default 15).
    """
    return _health_run(project_path, include_dead_code, include_refs, top)


@mcp.tool()
def explore_class_semantics(project_path: str, class_name: str,
                             summarize: bool = True, refresh: bool = False) -> str:
    """
    Get the full structure of a class with an optional AI-generated role summary.

    USE THIS TOOL WHEN:
    - User asks "what does class X do?"
    - User asks "show me the structure of X"
    - User is unfamiliar with a class and needs context before editing it
    - User asks "what methods / fields does X have?"
    - Before writing code that interacts with X

    Returns:
    - Fields, methods, in/out dependencies
    - Unity prefab / UE5 blueprint usages (engine asset back-references)
    - 3-line AI summary of the class role (cached in .gdep_cache/summaries/)

    Args:
        project_path: Absolute path to Scripts/Source folder.
        class_name:   Class to explore. E.g. "ManagerBattle", "AHSAttributeSet"
        summarize:    Prepend AI 3-line summary (requires gdep config llm). Default True.
        refresh:      Ignore cache and regenerate summary. Default False.
    """
    return _semantics_run(project_path, class_name, summarize, refresh)


# ════════════════════════════════════════════════════════════════
# RAW CLI ACCESS TOOL
# ════════════════════════════════════════════════════════════════

@mcp.tool()
def execute_gdep_cli(args: list[str]) -> str:
    """
    Execute any gdep CLI command directly. Use this to access features not covered
    by the high-level tools above.

    You MUST provide exact CLI arguments as a list of strings.

    Common examples:
      Detect project type:    ["detect", "D:/MyGame/Assets/Scripts"]
      Scan with dead code:    ["scan", "D:/MyGame/Assets/Scripts", "--dead-code", "--circular"]
      Describe a class:       ["describe", "D:/MyGame/Assets/Scripts", "BattleManager"]
      Flow trace (console):   ["flow", "D:/MyGame/Assets/Scripts", "--class", "BattleManager", "--method", "StartBattle"]
      Impact analysis:        ["impact", "D:/MyGame/Assets/Scripts", "BattleManager", "--depth", "5"]
      Lint check:             ["lint", "D:/MyGame/Assets/Scripts"]
      Graph export:           ["graph", "D:/MyGame/Assets/Scripts", "--format", "mermaid"]
      Diff vs HEAD~1:         ["diff", "D:/MyGame/Assets/Scripts", "--commit", "HEAD~1"]
      Generate hints:         ["hints", "generate", "D:/MyGame/Assets/Scripts"]
      Show LLM config:        ["config", "llm"]

    Args:
        args: CLI argument list (exclude 'gdep' itself).
              E.g. ["scan", "D:\\Project", "--dead-code"] runs: gdep scan D:\\Project --dead-code
    """
    try:
        command = [sys.executable, "-m", "gdep.cli"] + args

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            stdin=subprocess.DEVNULL,
            env=env,
            timeout=180,
            cwd=str(_GDEP_ROOT),
        )

        if result.returncode == 0:
            output = result.stdout or ""
            if result.stderr and result.stderr.strip():
                output = (output.rstrip("\n") + "\n\n" if output.strip() else "") + result.stderr.strip()
            return output or "(No output)"
        return (
            f"CLI Error (exit {result.returncode}):\n"
            f"{result.stderr}\n"
            f"{result.stdout}"
        )

    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 180 seconds."
    except Exception as e:
        return f"Failed to execute CLI command: {e}"


# ════════════════════════════════════════════════════════════════
# TEST SCOPE TOOL
# ════════════════════════════════════════════════════════════════

@mcp.tool()
def suggest_test_scope(project_path: str, class_name: str, depth: int = 3) -> str:
    """
    Suggest which test files need to run when a specific class is modified.

    USE THIS TOOL WHEN:
    - User asks "what tests do I need to run after changing class X?"
    - User asks "which tests cover class X?"
    - PR review: determine the minimal test set for a change
    - CI automation: generate a targeted test-file list programmatically
    - User says "I'm about to modify X, what should I test?"

    Performs reverse-dependency analysis (like analyze_impact_and_risk) and then
    filters the affected class list to test files only, using engine-specific patterns:
      - Unity / .NET : *Test*.cs  *Tests.cs  *Spec.cs  or  Tests/ directory
      - UE5          : *Spec.cpp  *Test*.cpp            or  Tests/ Specs/ directory
      - C++          : *test*.cpp *spec*.cpp test_*.cpp or  tests/ directory

    Returns:
    - Number of directly affected classes
    - List of test files that cover the affected scope, with engine tag and matched class

    Args:
        project_path: Absolute path to Scripts (Unity) or Source (UE5) folder.
        class_name:   Class to analyze. E.g. "BattleManager", "APlayerCharacter"
        depth:        Reverse-dependency tracing depth (default 3).
    """
    return _test_scope_run(project_path, class_name, depth)


# ════════════════════════════════════════════════════════════════
# LINT FIX TOOL
# ════════════════════════════════════════════════════════════════

@mcp.tool()
def suggest_lint_fixes(project_path: str, rule_ids: list[str] | None = None) -> str:
    """Run linter and return actionable code fix suggestions for detected anti-patterns.

    Goes beyond reporting — provides concrete code snippets for each fixable issue.
    Currently supports: UNI-PERF-001, UNI-PERF-002, UE5-BASE-001, UNI-ASYNC-001.

    USE THIS TOOL WHEN:
    - User asks 'how do I fix these lint warnings?'
    - After analyze_impact_and_risk reveals anti-patterns
    - Pre-PR cleanup: user wants concrete steps, not just a list

    Args:
        project_path: Absolute path to project root or Scripts/Source directory.
        rule_ids: Optional list of rule IDs to filter (e.g. ['UNI-PERF-001']).
    """
    return _lint_fixes_run(project_path, rule_ids=rule_ids)


# ════════════════════════════════════════════════════════════════
# DIFF SUMMARY TOOL
# ════════════════════════════════════════════════════════════════

@mcp.tool()
def summarize_project_diff(project_path: str,
                            commit_ref: str | None = None) -> str:
    """
    Analyze git diff and summarize the architectural impact of changes.

    USE THIS TOOL WHEN:
    - User asks "what does this PR do to the codebase architecture?"
    - User asks "does this change introduce new circular dependencies?"
    - User asks "is this commit risky from an architecture standpoint?"
    - PR review: need to understand structural impact, not just file changes
    - After refactoring: verify circular references were resolved

    Returns:
    - Number of changed files
    - New vs resolved circular references (net change)
    - High-coupling classes involved in new cycles (blast-radius warning)
    - Actionable review recommendations

    Args:
        project_path: Absolute path to project root or Scripts/Source directory.
        commit_ref:   Git ref to diff against (e.g. "HEAD~1", "main", a commit SHA).
                      Defaults to "HEAD~1".

    Note: Currently supports Unity / C# projects. For UE5/C++ use inspect_architectural_health.
    """
    return _diff_summary_run(project_path, commit_ref=commit_ref)


# ════════════════════════════════════════════════════════════════
# AXMOL-SPECIFIC TOOLS
# ════════════════════════════════════════════════════════════════

@mcp.tool()
def analyze_axmol_events(project_path: str,
                          class_name: str | None = None) -> str:
    """
    Scan an Axmol project for EventDispatcher and scheduler callback bindings.

    USE THIS TOOL WHEN:
    - User asks "which callbacks does this Axmol class register?"
    - User asks "where is this method wired as an event callback?"
    - Debugging event listener leaks or unexpected callback invocations
    - Reviewing which classes opt in to the scheduler (scheduleUpdate)

    Detects:
    - addEventListenerWithSceneGraphPriority / addEventListenerWithFixedPriority
    - CC_CALLBACK_0/1/2/3(ClassName::method, this) macro bindings
    - schedule / scheduleOnce with CC_SCHEDULE_SELECTOR(ClassName::method)
    - scheduleUpdate() registrations (implicit update() callback)

    Args:
        project_path: Absolute path to Axmol project root or Classes/ directory.
        class_name:   Optional class name to filter results.
                      If None, returns all bindings in the project.
    """
    return _axmol_events_run(project_path, class_name)


# ════════════════════════════════════════════════════════════════
# UNITY-SPECIFIC TOOLS (3단계 기능)
# ════════════════════════════════════════════════════════════════

@mcp.tool()
def find_unity_event_bindings(project_path: str,
                               method_name: str | None = None) -> str:
    """
    Find Unity Event (UnityEvent / Button.onClick) bindings in prefabs, scenes, and assets.

    Scans .prefab, .unity, and .asset files for persistent call bindings
    (m_PersistentCalls) and returns which methods are wired to which events.

    This reveals methods that are called from the Inspector (not visible in code search).

    Args:
        project_path: Absolute path to Unity Assets or Scripts folder.
        method_name:  Optional filter — only return bindings for this method name.
                      If None, returns all event bindings found.
    """
    if not _UNITY_EVENTS_AVAILABLE:
        return (
            "unity_event_refs module not available yet. "
            "Use execute_gdep_cli(['scan', project_path]) as a fallback."
        )
    try:
        from gdep.unity_event_refs import build_event_map, format_event_result
        event_map = build_event_map(project_path)
        return format_event_result(event_map, method_name)
    except Exception as e:
        return f"[find_unity_event_bindings] Error: {e}"


@mcp.tool()
def analyze_unity_animator(project_path: str,
                            controller_name: str | None = None) -> str:
    """
    Analyze Unity Animator Controller structure: layers, states, transitions, blend trees.

    Parses .controller files (Unity YAML) and returns a structured view of
    the animation state machine — layers, states, any-state transitions, blend trees,
    and which animation clips each state uses.

    Args:
        project_path:     Absolute path to Unity Assets or project root.
        controller_name:  Optional — analyze only the named .controller file.
                          If None, analyzes all .controller files found.
    """
    if not _UNITY_ANIMATOR_AVAILABLE:
        return (
            "unity_animator module not available yet. "
            "Use execute_gdep_cli(['detect', project_path]) as a fallback."
        )
    try:
        from gdep.unity_animator import analyze_animator
        return analyze_animator(project_path, controller_name)
    except Exception as e:
        return f"[analyze_unity_animator] Error: {e}"


# ════════════════════════════════════════════════════════════════
# UE5-SPECIFIC TOOLS (5~7단계 기능)
# ════════════════════════════════════════════════════════════════

@mcp.tool()
def analyze_ue5_gas(project_path: str,
                    class_name: str | None = None,
                    detail_level: str = "summary",
                    category: str | None = None,
                    query: str | None = None) -> str:
    """
    Analyze Gameplay Ability System (GAS) usage in a UE5 project.

    ⚠️ CRITICAL: Always call with detail_level="summary" first.
    Only use detail_level="full" if the user explicitly requests the full GAS report.
    Large projects may have 100+ tags — use category= or query= to narrow results before using "full".

    Scans C++ source and .uasset binaries to extract:
    - GameplayTags used (FGameplayTag, FGameplayTagContainer)
    - GameplayAbilities and their activation conditions
    - GameplayEffects and their targets
    - AttributeSets and their attributes
    - AbilitySystemComponent usage
    - ABP (AnimBlueprint) relationships to abilities

    Args:
        project_path: Absolute path to UE5 Source or project root.
        class_name:   Optional — filter results to a specific class.
                      If None, scans the entire project.
        detail_level: "summary" (default) — compact overview with tag distribution.
                      "full" — complete report (expensive; may return 100+ tags for large projects).
        category:     Tag prefix filter. e.g. "Event" → only Event.* tags and
                      abilities/effects that reference those tags.
        query:        Keyword search across class names, tag names, and asset names
                      (case-insensitive substring match).

    Usage examples:
        analyze_ue5_gas(path)                          # compact summary (always start here)
        analyze_ue5_gas(path, category="Event")        # Event.* tags only
        analyze_ue5_gas(path, query="Dash")            # everything related to Dash
        analyze_ue5_gas(path, detail_level="full")     # full report (only if user explicitly asked)
    """
    if not _UE5_GAS_AVAILABLE:
        return (
            "ue5_gas_analyzer module not available yet. "
            "Use execute_gdep_cli(['scan', project_path, '--deep']) as a fallback."
        )
    try:
        from gdep.ue5_gas_analyzer import analyze_gas
        return analyze_gas(project_path, class_name, detail_level, category, query)
    except Exception as e:
        return f"[analyze_ue5_gas] Error: {e}"


@mcp.tool()
def analyze_ue5_behavior_tree(project_path: str,
                               asset_name: str | None = None) -> str:
    """
    Extract and describe UE5 Behavior Tree structure from .uasset files.

    Parses BehaviorTree assets to reveal:
    - Root → Composite → Task/Decorator/Service hierarchy
    - Referenced C++ Task/Decorator/Service class names
    - Blackboard asset and its keys
    - Connection between BT assets and the AI Controllers that use them

    Args:
        project_path: Absolute path to UE5 Content or project root.
        asset_name:   Optional .uasset filename (without extension) to analyze.
                      If None, scans all BehaviorTree assets found.
    """
    if not _UE5_AI_AVAILABLE:
        return (
            "ue5_ai_analyzer module not available yet. "
            "Use execute_gdep_cli(['describe', project_path, 'MyAIController']) as a fallback."
        )
    try:
        from gdep.ue5_ai_analyzer import analyze_behavior_tree
        return analyze_behavior_tree(project_path, asset_name)
    except Exception as e:
        return f"[analyze_ue5_behavior_tree] Error: {e}"


@mcp.tool()
def analyze_ue5_state_tree(project_path: str,
                            asset_name: str | None = None) -> str:
    """
    Extract and describe UE5 StateTree structure from .uasset files.

    Parses StateTree assets (UE 5.2+) to reveal:
    - State hierarchy and transitions
    - Task/Evaluator/Condition C++ class references
    - Enter/Exit conditions per state
    - Linked schema and context data

    Args:
        project_path: Absolute path to UE5 Content or project root.
        asset_name:   Optional asset filename to analyze. If None, scans all StateTree assets.
    """
    if not _UE5_AI_AVAILABLE:
        return "ue5_ai_analyzer module not available yet."
    try:
        from gdep.ue5_ai_analyzer import analyze_state_tree
        return analyze_state_tree(project_path, asset_name)
    except Exception as e:
        return f"[analyze_ue5_state_tree] Error: {e}"


@mcp.tool()
def analyze_ue5_animation(project_path: str,
                           asset_name: str | None = None,
                           asset_type: str = "all",
                           detail_level: str = "summary") -> str:
    """
    Analyze UE5 animation assets: AnimBlueprint (ABP) and Animation Montages.

    USE THIS TOOL WHEN:
    - User asks "what animation states does this character have?"
    - User asks "which montages are used for abilities?"
    - User asks "what GAS notifies are in the animation?"
    - User needs to understand the animation graph structure

    detail_level controls output verbosity:
    - "summary" (default): Only gameplay-relevant info — State names, Slot names,
                           GAS-related notifies, referenced anim assets.
                           Best for understanding the animation system.
    - "full": Everything above + all AnimNotify classes, all asset references.
              Best for detailed debugging or documentation.

    Extracts:
    - ABP: state machine states (Idle/Jump/Attack etc.), slots, GAS ability notifies
    - Montage: section names, slot names, GAS notify events, AnimSequence references

    Args:
        project_path: Absolute path to UE5 Content or project root.
        asset_name:   Optional asset name filter. If None, scans all animation assets.
        asset_type:   One of "abp", "montage", or "all" (default).
        detail_level: "summary" (default) or "full".
    """
    if not _UE5_ANIMATOR_AVAILABLE:
        return "ue5_animator module not available yet."
    try:
        from gdep.ue5_animator import analyze_abp, analyze_montage

        def _trim_for_summary(text: str) -> str:
            """summary 모드: 노이즈 섹션 제거."""
            keep_sections = {
                "# AnimBlueprint", "# Animation Montage",
                "## ", "### States", "### Animation Slots",
                "### GAS-related", "### Sections", "### Slots",
                "### Referenced Anim",
            }
            out = []
            skip = False
            for line in text.splitlines():
                # 섹션 헤더
                if line.startswith("###"):
                    skip = not any(k in line for k in [
                        "States", "Animation Slots", "GAS-related",
                        "Sections", "Slots", "Referenced Anim"
                    ])
                if not skip:
                    out.append(line)
            return "\n".join(out)

        if asset_type == "abp":
            result = analyze_abp(project_path, asset_name)
        elif asset_type == "montage":
            result = analyze_montage(project_path, asset_name)
        else:
            result = analyze_abp(project_path, asset_name) + \
                     "\n\n" + analyze_montage(project_path, asset_name)

        return result if detail_level == "full" else _trim_for_summary(result)
    except Exception as e:
        return f"[analyze_ue5_animation] Error: {e}"


@mcp.tool()
def analyze_ue5_blueprint_mapping(project_path: str,
                                   cpp_class: str | None = None) -> str:
    """
    Blueprint <-> C++ detailed mapping for a UE5 project.

    USE THIS TOOL WHEN:
    - User asks "which Blueprints extend C++ class X?"
    - User asks "what does BP_Character implement?"
    - User asks "which events / K2 functions does this Blueprint override?"
    - User asks "what variables and assets are configured in this Blueprint?"
    - User wants to understand the bridge between C++ and Blueprint logic

    Scans all .uasset files and extracts for each Blueprint:
    - cpp_parent     The C++ parent class (NativeParentClass)
    - bp_class       The Blueprint-generated _C class name
    - event_nodes    Entry points in the event graph with call chains
    - k2_overrides   C++ virtual functions overridden in Blueprint (K2_ prefix)
    - variables      Blueprint-declared variables with type hints
    - asset_refs     /Game/ assets referenced (montages, GEs, other BPs)
    - gameplay_tags  GameplayTag values configured in this Blueprint
    - gas_params     GAS-specific settings (ActivationOwnedTags, etc.)
    - cpp_refs       Additional C++ types used beyond the direct parent

    Args:
        project_path: Absolute path to UE5 Source or project root.
        cpp_class:    Optional C++ class name to filter.
                      If provided, returns only Blueprints that extend this class.
                      If None, returns the full project-level summary.

    Examples:
        analyze_ue5_blueprint_mapping(path)
            -> Full map: lists every C++ class and its BP implementations
        analyze_ue5_blueprint_mapping(path, "AHSCharacterBase")
            -> Shows all BPs that extend AHSCharacterBase with events + variables
        analyze_ue5_blueprint_mapping(path, "UGameplayAbility")
            -> Shows all GA Blueprints with K2_ActivateAbility chains + tags
    """
    if not _UE5_BP_MAPPING_AVAILABLE:
        return "ue5_blueprint_mapping module not available."
    try:
        from gdep.ue5_blueprint_mapping import build_bp_map, format_full_project_map
        bp_map = build_bp_map(project_path)
        if not bp_map.blueprints:
            return (
                f"No Blueprint assets found for project at '{project_path}'.\n"
                "This may happen if:\n"
                "- The Content folder is empty or missing\n"
                "- Assets are stored via Git LFS and not pulled yet\n"
                "- The project path points to Source only (not project root)\n"
                "Try passing the project root instead of the Source folder."
            )
        return format_full_project_map(bp_map, cpp_class)
    except Exception as e:
        return f"[analyze_ue5_blueprint_mapping] Error: {e}"


@mcp.tool()
def get_architecture_advice(project_path: str,
                             focus_class: str | None = None) -> str:
    """
    Diagnose the architecture of a game project and suggest improvements.

    Combines scan (coupling/cycles/dead-code) + lint (anti-patterns) +
    impact analysis for the highest-risk class into a single advice report.

    If an LLM is configured (gdep config llm), the report is enriched with
    natural-language advice from the model. Results are cached in
    .gdep/cache/advice.md and reused until project metrics change.

    USE THIS TOOL WHEN:
    - User asks "what is the technical debt in this project?"
    - User asks "what should I refactor first?"
    - User asks "diagnose the architecture problems"
    - User asks "give me refactoring priorities"
    - User wants a high-level overview before starting a large change

    Args:
        project_path: Absolute path to the project root or source directory.
        focus_class:  Optional class name to center the advice around.
                      Impact analysis will pivot on this class.
                      If None, the highest-coupling class is used automatically.
    """
    try:
        from gdep.detector import detect
        from gdep import runner
        profile = detect(project_path)
        result = runner.advise(profile, focus_class=focus_class)
        if not result.ok:
            return f"[get_architecture_advice] Error: {result.error_message}"
        return result.stdout
    except Exception as e:
        return f"[get_architecture_advice] Error: {e}"


@mcp.tool()
def explain_method_logic(project_path: str, class_name: str, method_name: str) -> str:
    """
    Extract and summarize the internal control flow logic of a specific method.

    Unlike trace_gameplay_flow (which shows the call chain A→B→C),
    this tool focuses on WHY and WHEN calls happen inside a single method —
    returning guard conditions, branches, loops, and key calls in 5-10 lines.

    USE THIS TOOL WHEN:
    - User asks "what does method X actually do internally?"
    - User asks "what are the conditions inside PlayHand / ActivateAbility?"
    - User wants to understand business rules without reading the full source file
    - User asks "when does this method return early?"
    - User is debugging conditional logic or branching behavior

    Returns:
    - Numbered list of Guard / Branch / Loop / Always control flow items
    - Each item shows the condition and 1-2 key calls made in that branch
    - Source file reference for quick navigation

    Args:
        project_path: Absolute path to the project root or source folder.
        class_name:   Class containing the method. E.g. "ManagerBattle", "AHSCharacterBase"
        method_name:  Method to explain. E.g. "PlayHand", "ActivateAbility", "BeginPlay"
    """
    return _explain_logic_run(project_path, class_name, method_name)


# ════════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    mcp.run()
