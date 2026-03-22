"""
gdep CLI
Usage: gdep <command> [options]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from . import runner
from .detector import ProjectKind, detect

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"], max_content_width=100)


# ── Common Options ───────────────────────────────────────────

_profile_cache: dict = {}

def _get_profile(path: str):
    if path in _profile_cache:
        return _profile_cache[path]
    # ── Disk cache for detect result (~4s → ~0.1s on warm) ──
    import hashlib
    import json as _json
    import time as _time
    from pathlib import Path as _Path
    _cache_dir = _Path(path).resolve().parent / ".gdep_cache"
    _cache_dir.mkdir(exist_ok=True)
    _cache_file = _cache_dir / "detect.json"
    # Invalidate if any .cs / .h / .cpp / .uproject / .csproj changed
    _sig_files = (
        list(_Path(path).glob("*.uproject")) +
        list(_Path(path).glob("*.csproj")) +
        list(_Path(path).parent.glob("*.uproject"))
    )
    _sig = hashlib.md5(
        "|".join(f"{f}:{f.stat().st_mtime_ns}" for f in sorted(_sig_files) if f.exists()).encode()
    ).hexdigest() if _sig_files else "static"
    try:
        _cached = _json.loads(_cache_file.read_text(encoding="utf-8"))
        if _cached.get("sig") == _sig:
            profile = detect(path)  # still need object, but avoid full scan
            _profile_cache[path] = profile
            return profile
    except Exception:
        pass
    profile = detect(path)
    try:
        _cache_file.write_text(
            _json.dumps({"sig": _sig, "saved_at": _time.time(), "kind": str(profile.kind)}),
            encoding="utf-8"
        )
    except Exception:
        pass
    _profile_cache[path] = profile
    return profile


def _print_profile(profile, verbose: bool = False):
    click.echo(f"  Project:  {profile.name}")
    click.echo(f"  Type:     {profile.display}")
    click.echo(f"  Root:     {profile.root}")
    if profile.source_dirs:
        click.echo(f"  Source:   {profile.source_dirs[0]}")
    if verbose and profile.extra:
        for k, v in profile.extra.items():
            click.echo(f"  {k}: {v}")


# ── CLI Group ────────────────────────────────────────────────

@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option("0.1.0", prog_name="gdep")
def cli():
    """gdep — Game Codebase Analysis Tool for Humans and AI Agents

    \b
    Supports: Unity (C#) · Cocos2d-x (C++) · Unreal Engine 5 · .NET · C++
    Auto-detects project type from the given path.

    \b
    Quick start:
      gdep detect  <path>                   # Check project type
      gdep scan    <path> --circular        # Coupling + cycle analysis
      gdep describe <path> <ClassName>      # Class structure
      gdep flow    <path> --class X --method Y   # Call flow trace
      gdep impact  <path> <ClassName>       # Change impact (reverse deps)
      gdep lint    <path>                   # Anti-pattern scan
      gdep diff    <path>                   # Dependency diff (git)
      gdep init    <path>                   # Create .gdep/AGENTS.md for AI Agents
      gdep context <path>                   # Print project context for AI
      gdep hints   generate <path>          # Generate hint file
      gdep config  llm                      # LLM provider settings
    """
    pass


# ── detect ───────────────────────────────────────────────────

@cli.command(context_settings=CONTEXT_SETTINGS, epilog="""
\b
Examples:
  gdep detect .
  gdep detect D:\\MyGame\\Assets\\Scripts
  gdep detect /home/user/MyGame --json
""")
@click.argument("path", default=".", metavar="PATH")
@click.option("--json", "as_json", is_flag=True, help="Output result as JSON")
def detect_cmd(path, as_json):
    """Auto-detect project engine and language from PATH.

    \b
    Inspects directory structure and file patterns to identify:
      Unity (C#), Unreal Engine 5 (C++), Cocos2d-x (C++), .NET (C#), generic C++

    Use this first to confirm the path is correctly recognized before running
    other commands. Useful in CI scripts to dynamically branch by engine type.
    """
    profile = _get_profile(path)

    if as_json:
        click.echo(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2))
        return

    click.echo()
    click.secho("── Project Detection Result ─────────────", fg="cyan")
    _print_profile(profile, verbose=True)

    if profile.kind == ProjectKind.UNKNOWN:
        _safe_echo("\n[WARN] Could not detect project type.", fg="yellow")
        click.echo("   Use --kind to specify manually, or check the path.")
    else:
        click.echo(f"\nDetected as {profile.display} project.")

    click.echo()


# ── scan ─────────────────────────────────────────────────────

@cli.command(context_settings=CONTEXT_SETTINGS, epilog="""
\b
Examples:
  # Basic coupling report (top 20)
  gdep scan D:\\MyGame\\Assets\\Scripts

  # Circular dependency detection + top 30
  gdep scan . --circular --top 30

  # Dead code detection with prefab/blueprint back-reference filtering
  gdep scan . --dead-code --include-refs

  # Deep method-body analysis for accurate coupling in UE5
  gdep scan . --deep

  # Filter by namespace, exclude generated files
  gdep scan . --namespace Game.Battle --ignore "*_PROTO.cs" --ignore "*.g.cs"

  # Export as JSON for AI agent or pipeline use
  gdep scan . --format json > report.json
""")
@click.argument("path", default=".", metavar="PATH")
@click.option("--circular",      is_flag=True, help="Detect circular dependencies")
@click.option("--dead-code",     is_flag=True, help="Detect unreferenced classes (in-degree 0)")
@click.option("--deep",          is_flag=True, help="Analyze method bodies for deeper coupling (C#, UE5)")
@click.option("--include-refs",  is_flag=True, help="Factor in engine asset refs (Prefab/Blueprint) for dead-code filtering")
@click.option("--top",           default=20, show_default=True, metavar="N", help="Show top N high-coupling classes")
@click.option("--namespace",     default=None, metavar="NS", help="Filter to a specific namespace")
@click.option("--ignore",        multiple=True, metavar="PATTERN", help="Exclude file patterns (repeatable, e.g. --ignore '*.g.cs')")
@click.option("--format", "fmt", default="console", show_default=True,
              type=click.Choice(["console", "json", "mermaid", "dot"]),
              help="Output format")
@click.option("--kind",          default=None,
              type=click.Choice(["unity", "dotnet", "cpp", "unreal"]),
              help="Force project type (skip auto-detect)")
def scan(path, circular, dead_code, deep, include_refs, top, namespace, ignore, fmt, kind):
    """Analyze class coupling and detect circular/dead-code issues.

    \b
    Outputs:
      - Coupling rank: classes sorted by in-degree (how many others reference them)
      - Circular dependencies: direct and indirect cycles
      - Dead code: classes with zero references (optionally filtered by engine asset refs)

    \b
    When to use:
      - Onboarding to a new codebase: understand which classes are most critical
      - Before refactoring: find highly coupled classes and circular deps
      - CI quality gate: use --format json and parse deadNodes/cycles programmatically
    """
    profile = _get_profile(path)
    if not _check_supported(profile, kind):
        return
    _safe_echo(f"scan  [{profile.display}]  {profile.source_dirs[0]}", fg="cyan")
    result = runner.scan(profile, circular=circular, dead_code=dead_code,
                         deep=deep, include_refs=include_refs,
                         top=top, namespace=namespace,
                         ignore=list(ignore), fmt=fmt)
    _print_result(result)


# ── describe ─────────────────────────────────────────────────

@cli.command(context_settings=CONTEXT_SETTINGS, epilog="""
\b
Examples:
  # Console output (default)
  gdep describe . ManagerBattle

  # Mermaid class diagram saved to file
  gdep describe . ManagerBattle --format mermaid --output docs/battle.md

  # AI-powered 3-line role summary (requires LLM config)
  gdep describe . ManagerBattle --summarize

  # Force regenerate cached summary
  gdep describe . ManagerBattle --summarize --refresh
""")
@click.argument("path",       default=".", metavar="PATH")
@click.argument("class_name", metavar="CLASS")
@click.option("--format", "fmt", default="console", show_default=True,
              type=click.Choice(["console", "mermaid", "dot"]),
              help="Output format")
@click.option("--output",    default=None, metavar="FILE", help="Save output to file")
@click.option("--summarize", is_flag=True, help="Prepend AI-generated 3-line role summary (cached)")
@click.option("--refresh",   is_flag=True, help="Bypass summary cache and regenerate")
def describe(path, class_name, fmt, output, summarize, refresh):
    """Show detailed structure of a single class.

    \b
    Outputs for each class:
      - Inheritance / interfaces
      - Fields and properties (with types and access modifiers)
      - Methods (with return types, parameters, async/virtual flags)
      - Out-degree: classes this class depends on
      - In-degree: classes that reference this class
      - Unity: prefab/scene usages  |  UE5: blueprint usages

    \b
    When to use:
      - Code review: quickly understand what a class does without opening the file
      - LLM context: pipe output as system context before asking about the class
      - Documentation: export Mermaid diagrams for Confluence/Notion
    """
    profile = _get_profile(path)
    _safe_echo(f"► describe  [{profile.display}]  {class_name}", fg="cyan")
    result = runner.describe(profile, class_name, fmt=fmt,
                             summarize=summarize, refresh=refresh)
    if output and result.ok:
        ext = ".dot" if fmt == "dot" else ".md"
        out_path = output if "." in Path(output).name else output + ext
        Path(out_path).write_text(result.stdout, encoding="utf-8")
        _safe_echo(f"✓  Saved to: {out_path}", fg="green")
    else:
        _print_result(result)


# ── flow ─────────────────────────────────────────────────────

@cli.command(context_settings=CONTEXT_SETTINGS, epilog="""
\b
Examples:
  # Trace call flow from ManagerBattle.PlayHand (depth 4)
  gdep flow . --class ManagerBattle --method PlayHand

  # Deeper trace with focus on specific classes
  gdep flow . --class ManagerBattle --method PlayHand --depth 6 --focus-class BattleCore,CardEffect

  # Export as JSON for React Flow / custom visualization
  gdep flow . --class UIBattle --method OnClickEndTurn --format json --output flow.json

  # Export Mermaid flowchart for documentation
  gdep flow . --class GameManager --method StartGame --format mermaid --output docs/startgame.md

\b
Hint file (for singleton chain patterns like Managers.Battle.DoSomething()):
  gdep hints generate .     # auto-generate .gdep-hints.json
  gdep hints show    .      # verify registered mappings
""")
@click.argument("path", default=".", metavar="PATH")
@click.option("--class",        "class_name",    required=True,  metavar="CLASS",  help="Entry point class name")
@click.option("--method",       "method_name",   required=True,  metavar="METHOD", help="Entry point method name")
@click.option("--depth",        default=4, show_default=True,    metavar="N",      help="Call chain tracing depth (1–10)")
@click.option("--focus-class",  "focus_classes", default=None,   metavar="CLASSES",help="Comma-separated classes to trace deeply")
@click.option("--format", "fmt", default="console", show_default=True,
              type=click.Choice(["console", "json", "mermaid", "dot"]),
              help="Output format")
@click.option("--output",       default=None, metavar="FILE", help="Save output to file")
@click.option("--kind",         default=None,
              type=click.Choice(["unity", "dotnet", "cpp", "unreal"]),
              help="Force project type")
def flow(path, class_name, method_name, depth, focus_classes, fmt, output, kind):
    """Trace method call chain as a tree.

    \b
    Renders a call tree starting from CLASS.METHOD, following actual invocations
    up to DEPTH levels. Annotates async, lock, dispatch, and leaf nodes.

    \b
    Legend:
      async   — awaited async call
      lock    — inside lock/mutex block
      ⇢       — dynamic dispatch (event/delegate/signal)
      ○       — leaf node (no further calls found)
      ?       — unresolved call (needs hint file)

    \b
    When to use:
      - Bug tracing: follow the path from entry point to the problem site
      - Onboarding: show new developers what a feature actually does at runtime
      - LLM context: export JSON and include in prompt for precise code Q&A
      - Performance: trace async chains to spot unintended blocking calls
    """
    profile = _get_profile(path)
    if not _check_supported(profile, kind):
        return
    focus = [f.strip() for f in focus_classes.split(",")] if focus_classes else None
    click.secho(
        f"► flow  [{profile.display}]  {class_name}.{method_name}  depth={depth}",
        fg="cyan"
    )
    result = runner.flow(profile, class_name, method_name,
                         depth=depth, focus_classes=focus, fmt=fmt)
    if output and result.ok:
        ext = ".dot" if fmt == "dot" else ".md" if fmt == "mermaid" else ".json"
        out_path = output if "." in Path(output).name else output + ext
        Path(out_path).write_text(result.stdout, encoding="utf-8")
        _safe_echo(f"✓  Saved to: {out_path}", fg="green")
    else:
        _print_result(result)


# ── impact ───────────────────────────────────────────────────

@cli.command(context_settings=CONTEXT_SETTINGS, epilog="""
\b
Examples:
  # Who would be affected if I change ManagerBattle?
  gdep impact . ManagerBattle

  # Wider blast radius (depth 5)
  gdep impact . DataManager --depth 5

  # Force Unity project type
  gdep impact . CardEffect --kind unity
""")
@click.argument("path",         default=".",  metavar="PATH")
@click.argument("target_class", metavar="CLASS")
@click.option("--depth", default=3, show_default=True, metavar="N",
              help="Reverse dependency tracing depth")
@click.option("--kind",  default=None,
              type=click.Choice(["unity", "dotnet", "cpp", "unreal"]),
              help="Force project type")
def impact(path, target_class, depth, kind):
    """Show which classes are affected if CLASS is changed.

    \b
    Performs a reverse-dependency BFS from CLASS up to DEPTH levels.
    Shows the 'blast radius' of a change: who calls this, and who calls them.

    \b
    Output:
      ClassName (source_file.cs)
      ├── Dependent1 (file.cs)
      │   └── Dependent2 (file.cs)  [RECURSIVE if cycle detected]
      └── Dependent3 (file.cs)

    \b
    Unity: also appends prefab/scene asset usages at the bottom.

    \b
    When to use:
      - Before modifying a class: estimate how many files need retesting
      - PR review: quickly assess the scope of a change
      - Refactoring planning: find safe leaf nodes vs. highly-impacted hubs
    """
    profile = _get_profile(path)
    if not _check_supported(profile, kind):
        return
    _safe_echo(f"► impact  [{profile.display}]  {target_class}  depth={depth}", fg="cyan")
    result = runner.impact(profile, target_class, depth=depth)
    _print_result(result)


# ── lint ─────────────────────────────────────────────────────

@cli.command(context_settings=CONTEXT_SETTINGS, epilog="""
\b
Examples:
  # Console output with rule IDs and suggestions
  gdep lint D:\\MyGame\\Assets\\Scripts

  # JSON output for CI integration / custom reporting
  gdep lint . --format json > lint_report.json

  # Force engine type
  gdep lint . --kind unreal
\b
Rule IDs:
  UNI-PERF-001  GetComponent/Find called inside Update lifecycle
  UNI-PERF-002  Object allocation (new / Instantiate) inside Update
  UNI-ASYNC-001 IEnumerator while(true) with no yield inside the loop
  UNI-ASYNC-002 Heavy Unity API (FindObjectOfType etc.) inside Coroutine
  UE5-PERF-001  Heavy operation (SpawnActor, LoadObject...) inside Tick
  UE5-PERF-002  Synchronous LoadObject inside BeginPlay
  UE5-BASE-001  Missing Super:: call in overridden lifecycle method
  UE5-GAS-001   ActivateAbility() missing CommitAbility() call
  UE5-GAS-002   Expensive world query (GetAllActorsOfClass...) inside Ability
  UE5-GAS-003   Excessive BlueprintCallable exposure (>10 on one class)
  UE5-GAS-004   BlueprintPure method missing const qualifier
  UE5-NET-001   Replicated property without ReplicatedUsing callback
  GEN-ARCH-001  Circular dependency detected
""")
@click.argument("path", default=".", metavar="PATH")
@click.option("--format", "fmt", default="console", show_default=True,
              type=click.Choice(["console", "json"]),
              help="Output format  (json is CI-friendly)")
@click.option("--kind",   default=None,
              type=click.Choice(["unity", "dotnet", "cpp", "unreal"]),
              help="Force project type")
def lint(path, fmt, kind):
    """Scan for engine-specific anti-patterns and performance issues.

    \b
    Checks source files for known bad patterns per engine:

    \b
    Unity (C#):
      - GetComponent / Find inside Update, FixedUpdate, LateUpdate  → GC pressure
      - new / Instantiate inside Update lifecycle                    → GC spikes

    \b
    Unreal Engine 5 (C++):
      - SpawnActor / NewObject / LoadObject inside Tick              → frame stalls
      - Synchronous LoadObject inside BeginPlay                      → hitch on load
      - Missing Super::BeginPlay / Super::Tick calls                 → silent bugs

    \b
    All engines:
      - Circular dependencies (GEN-ARCH-001)

    \b
    When to use:
      - Pre-PR check: catch performance regressions before review
      - Onboarding audit: quickly scan legacy code for anti-patterns
      - CI gate: use --format json and fail build on Error severity issues
    """
    profile = _get_profile(path)
    if not _check_supported(profile, kind):
        return
    _safe_echo(f"► lint  [{profile.display}]  {profile.source_dirs[0]}", fg="cyan")
    result = runner.lint(profile, fmt=fmt)
    _print_result(result)


# ── graph ─────────────────────────────────────────────────────

@cli.command(context_settings=CONTEXT_SETTINGS, epilog="""
\b
Examples:
  # Mermaid graph saved to file (paste into Notion / Confluence)
  gdep graph . --output docs/graph.md

  # Graphviz DOT → render as SVG
  gdep graph . --format dot --output graph.dot
  dot -Tsvg graph.dot -o graph.svg

  # Show only classes involved in cycles
  gdep graph . --cycles-only --format mermaid
""")
@click.argument("path", default=".", metavar="PATH")
@click.option("--format", "fmt", default="mermaid", show_default=True,
              type=click.Choice(["mermaid", "dot"]),
              help="Output format")
@click.option("--output",      default=None,  metavar="FILE", help="Save output to file")
@click.option("--cycles-only", is_flag=True,  help="Only include cycle-involved nodes")
@click.option("--no-isolated", is_flag=True,  help="Exclude isolated nodes (zero edges)")
def graph(path, fmt, output, cycles_only, no_isolated):
    """Export full dependency graph as Mermaid or Graphviz DOT.

    \b
    Generates a directed graph of all class dependencies.
    Circular dependency nodes are highlighted (⚠ prefix + red styling).

    \b
    When to use:
      - Architecture documentation: insert diagrams into wiki pages
      - Visual review: spot tangled subsystems at a glance
      - CI artifact: auto-generate updated graph on each merge to main
    """
    profile = _get_profile(path)
    _safe_echo(f"► graph  [{profile.display}]", fg="cyan")
    result = runner.graph(profile, fmt=fmt, output=output, cycles_only=cycles_only)
    _print_result(result)


# ── diff ─────────────────────────────────────────────────────

@cli.command(context_settings=CONTEXT_SETTINGS, epilog="""
\b
Examples:
  # Compare current state vs previous commit
  gdep diff . --commit HEAD~1

  # Compare against a branch
  gdep diff . --commit main

  # CI gate: exit code 1 if new circular deps are introduced
  gdep diff . --commit HEAD~1 --fail-on-cycles
""")
@click.argument("path", default=".", metavar="PATH")
@click.option("--commit",        default=None,  metavar="REF",
              help="Git ref to compare against (branch, tag, SHA). Default: HEAD~1")
@click.option("--fail-on-cycles", is_flag=True,
              help="Exit with code 1 if new circular dependencies are introduced (CI use)")
def diff(path, commit, fail_on_cycles):
    """Compare dependency state before and after a git commit.

    \b
    Reports:
      - New / removed classes
      - Coupling score changes (top movers)
      - Newly introduced circular dependencies

    \b
    When to use:
      - PR review: paste report in PR description to show architectural impact
      - CI pipeline: use --fail-on-cycles to block merges that introduce cycles
      - Post-refactor validation: confirm coupling actually decreased
    """
    profile = _get_profile(path)
    _safe_echo(f"► diff  [{profile.display}]", fg="cyan")
    result = runner.diff(profile, commit=commit, fail_on_cycles=fail_on_cycles)
    _print_result(result)
    if not result.ok and fail_on_cycles:
        sys.exit(1)


# ── hints ────────────────────────────────────────────────────

@cli.group(context_settings=CONTEXT_SETTINGS)
def hints():
    """Manage .gdep-hints.json for static accessor resolution.

    \b
    Hint files tell the flow tracer how to resolve singleton/static patterns
    like  Managers.Battle.PlayHand()  →  ManagerBattle.PlayHand()

    \b
    Without hints, calls through static accessors show as '? unresolved' in flow output.
    """
    pass


@hints.command("generate", context_settings=CONTEXT_SETTINGS, epilog="""
\b
Examples:
  gdep hints generate .
  gdep hints generate D:\\MyGame\\Assets\\Scripts
""")
@click.argument("path", default=".", metavar="PATH")
def hints_generate(path):
    """Auto-detect static accessor patterns and generate .gdep-hints.json.

    \b
    Scans source files for patterns like:
      public static ManagerBattle Battle => ...
      public static ManagerUI UI { get; private set; }

    Then writes a hint file:
      {
        "staticAccessors": {
          "Managers": { "Battle": "ManagerBattle", "UI": "ManagerUI" }
        }
      }

    Edit the file manually to add or fix missing mappings.
    """
    profile = _get_profile(path)
    _safe_echo(f"► hints generate  [{profile.display}]", fg="cyan")
    result = runner.hints_generate(profile)
    _print_result(result)


@hints.command("show", context_settings=CONTEXT_SETTINGS)
@click.argument("path", default=".", metavar="PATH")
def hints_show(path):
    """Print the current .gdep-hints.json content for PATH."""
    profile = _get_profile(path)
    result = runner.hints_show(profile)
    _print_result(result)


# ── config ───────────────────────────────────────────────────

@cli.group(context_settings=CONTEXT_SETTINGS)
def config():
    """Manage gdep configuration (LLM provider, API keys, etc.)."""
    pass


@config.command("llm", context_settings=CONTEXT_SETTINGS, epilog="""
\b
Examples:
  # Show current settings
  gdep config llm

  # Use local Ollama (default)
  gdep config llm --provider ollama --model qwen2.5-coder:14b

  # Use OpenAI GPT-4o
  gdep config llm --provider openai --model gpt-4o --api-key sk-...

  # Use Anthropic Claude
  gdep config llm --provider claude --model claude-sonnet-4-6 --api-key sk-ant-...

  # Use Google Gemini
  gdep config llm --provider gemini --model gemini-1.5-pro --api-key AIza...

  # Custom Ollama endpoint
  gdep config llm --provider ollama --base-url http://192.168.1.10:11434
""")
@click.option("--provider",  type=click.Choice(["ollama", "openai", "gemini", "claude"]),
              help="LLM provider to use")
@click.option("--model",     metavar="MODEL",   help="Model name")
@click.option("--api-key",   metavar="KEY",     help="API key (stored in ~/.gdep/llm_config.json)")
@click.option("--base-url",  metavar="URL",     help="API base URL (Ollama only, default: http://localhost:11434)")
def config_llm(provider, model, api_key, base_url):
    """View or update LLM provider settings used by --summarize and the AI agent.

    \b
    Settings are stored in ~/.gdep/llm_config.json.
    Required for: gdep describe --summarize
    """
    from .llm_provider import LLMConfig, load_config, save_config

    cfg = load_config() or LLMConfig(provider="ollama", model="qwen2.5-coder:14b")

    if not provider and not model and not api_key and not base_url:
        click.echo("\n── Current LLM Configuration ──────────")
        click.echo(f"  Provider:   {cfg.provider}")
        click.echo(f"  Model:      {cfg.model}")
        click.echo(f"  API Key:    {'*' * 8 if cfg.api_key else '(None)'}")
        click.echo(f"  Base URL:   {cfg.base_url}")
        return

    if provider: cfg.provider = provider
    if model:    cfg.model    = model
    if api_key:  cfg.api_key  = api_key
    if base_url: cfg.base_url = base_url

    save_config(cfg)
    _safe_echo(f"✓  LLM config saved  [{cfg.provider} / {cfg.model}]", fg="green")


# ── init ─────────────────────────────────────────────────────

@cli.command(context_settings=CONTEXT_SETTINGS, epilog="""
\b
Examples:
  gdep init .
  gdep init D:\\MyGame\\Assets\\Scripts
  gdep init F:\\MyUE5Project\\Source\\MyGame

\b
The generated .gdep/AGENTS.md file is automatically read by:
  - Claude Desktop (as project context)
  - Cursor AI (.cursorrules equivalent for game projects)
  - Gemini CLI (via GEMINI.md convention)
  - Any MCP-compatible AI agent
""")
@click.argument("path", default=".", metavar="PATH")
@click.option("--force", is_flag=True, help="Overwrite existing .gdep/AGENTS.md")
def init(path, force):
    """Initialize .gdep/AGENTS.md — teach AI Agents how to use gdep on this project.

    \b
    Creates a .gdep/AGENTS.md file at the project root containing:
      - Project type and source path (auto-detected)
      - Codebase snapshot: class count, high-coupling classes, dead code
      - Engine-specific info: GAS summary (UE5), Animator controllers (Unity)
      - MCP tool usage guide with project-specific paths pre-filled
      - Decision table: "which gdep tool to use for which question"

    \b
    After running this, AI Agents using gdep MCP will automatically:
      - Know the project's source path without asking
      - Understand which gdep tools to use for common tasks
      - Have a codebase overview before any conversation starts

    \b
    Re-run after major refactoring to refresh the snapshot.
    """
    from .detector import detect
    from .init_context import write_agents_md

    profile = detect(path)
    agents_md = Path(profile.root) / ".gdep" / "AGENTS.md"

    if agents_md.exists() and not force:
        _safe_echo(f"[WARN] {agents_md} already exists. Use --force to overwrite.", fg="yellow")
        return

    _safe_echo(f"► init  [{profile.display}]  {profile.root}", fg="cyan")
    click.echo("  Analyzing project...")

    try:
        agents_md = write_agents_md(path, force=force)
        content = agents_md.read_text(encoding="utf-8")
        click.secho(f"\n[OK] Created: {agents_md}", fg="green")
        click.echo(f"  {len(content.splitlines())} lines written.")
        click.echo()
        click.echo("  AI Agents (Claude Desktop, Cursor, Gemini CLI) will now automatically")
        click.echo("  read this file as project context when working in this directory.")
        click.echo()
        click.echo("  Add .gdep/ to .gitignore if you don't want to commit it,")
        click.echo("  or commit it to share context with your team.")
    except Exception as e:
        _safe_echo(f"\n[ERROR] Failed: {e}", fg="red", err=True)


# ── context ───────────────────────────────────────────────────

@cli.command(context_settings=CONTEXT_SETTINGS, epilog="""
\b
Examples:
  # Print context (copy-paste into AI chat)
  gdep context .

  # Pipe directly into clipboard (Windows)
  gdep context . | clip

  # Pipe directly into clipboard (macOS)
  gdep context . | pbcopy

  # Save to file
  gdep context . > project_context.md
""")
@click.argument("path", default=".", metavar="PATH")
def context(path):
    """Print AI-ready project context to stdout.

    \b
    If .gdep/AGENTS.md exists, prints its content.
    Otherwise, generates context on the fly (without saving).

    \b
    Use this to:
      - Copy-paste project context into any AI chat (ChatGPT, Claude.ai, etc.)
      - Pipe into clipboard for quick pasting
      - Check what context AI Agents see about this project

    \b
    For persistent context (auto-loaded by AI Agents), use 'gdep init' instead.
    """
    from .init_context import build_context_output
    try:
        output = build_context_output(path)
        click.echo(output)
    except Exception as e:
        _safe_echo(f"✗  Failed: {e}", fg="red", err=True)


# ── info ─────────────────────────────────────────────────────

@cli.command(context_settings=CONTEXT_SETTINGS)
def info():
    """Show gdep environment: gdep binary path, LLM config."""
    from .llm_provider import load_config

    click.echo()
    click.secho("── gdep Environment ─────────────────", fg="cyan")

    gdep = runner.find_gdep()
    if gdep:
        click.secho(f"  gdep binary:  {gdep.args}", fg="green")
        click.echo(f"  dll mode:     {'yes' if gdep.is_dll else 'no'}")
    else:
        _safe_echo("  gdep binary:  [NOT FOUND]", fg="red")
        click.echo("                Set GDEP_DLL / GDEP_EXE env var, or rebuild publish_dll/")

    cfg = load_config()
    if cfg:
        click.echo(f"  LLM provider: {cfg.provider}  /  {cfg.model}")
    else:
        _safe_echo("  LLM config:   (not configured -- run: gdep config llm --provider ...)", fg="yellow")

    click.echo()


# ── Utils ─────────────────────────────────────────────────────

def _safe_echo(msg: str, **kwargs):
    """click.secho wrapper that gracefully handles non-UTF-8 terminals (e.g. cp949 on Windows)."""
    try:
        click.secho(msg, **kwargs)
    except UnicodeEncodeError:
        # Strip non-ASCII characters and retry
        safe = msg.encode(sys.stdout.encoding or "ascii", errors="replace").decode(
            sys.stdout.encoding or "ascii"
        )
        click.secho(safe, **kwargs)


def _check_supported(profile, kind_override: str | None) -> bool:
    if kind_override:
        return True
    if profile.kind in (ProjectKind.UNITY, ProjectKind.DOTNET,
                        ProjectKind.CPP, ProjectKind.UNREAL):
        return True
    if profile.kind == ProjectKind.UNKNOWN:
        _safe_echo(
            "[WARN] Could not detect project type.\n"
            "   Please specify with --kind option.",
            fg="yellow"
        )
        return False
    _safe_echo(f"[WARN] {profile.display} projects are not yet supported.", fg="yellow")
    return False


def _print_result(result: runner.RunResult):
    if result.stdout:
        try:
            click.echo(result.stdout, nl=False)
        except UnicodeEncodeError:
            safe = result.stdout.encode(
                sys.stdout.encoding or "ascii", errors="replace"
            ).decode(sys.stdout.encoding or "ascii")
            click.echo(safe, nl=False)
    if not result.ok:
        _safe_echo(f"\n[ERROR] {result.error_message}", fg="red", err=True)


# ── Entry Point ───────────────────────────────────────────────

cli.add_command(detect_cmd, name="detect")

def main():
    cli()

if __name__ == "__main__":
    main()
