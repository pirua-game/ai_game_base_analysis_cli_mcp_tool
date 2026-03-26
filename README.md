# 🎮 gdep — Game Codebase Analysis Tool

**Understand a Unity/UE5/Axmol project in 0.5 seconds. Make Claude and Cursor read the actual code.**

[![CI](https://github.com/pirua-game/gdep/actions/workflows/ci.yml/badge.svg)](https://github.com/pirua-game/gdep/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/gdep)](https://pypi.org/project/gdep/)
[![npm](https://img.shields.io/npm/v/gdep-mcp)](https://www.npmjs.com/package/gdep-mcp)

> *"If I modify this class, what breaks?"* — answered in 3 seconds, zero hallucinations.
> Measured: **100% accuracy** with MCP (code-based facts) vs hallucinations without

**Read this in other languages:**
[한국어](./README_KR.md) · [日本語](./README_JA.md) · [简体中文](./README_ZH.md) · [繁體中文](./README_ZH_TW.md)

---

## ✨ Why gdep?

Large game codebases are brutal:

- UE5 with 300+ Blueprints → *"Where is this Ability actually called?"* — half a day gone
- Unity with 50 Managers + Prefab refs → refactor triggers circular dep explosion
- *"What breaks if I change this class?"* → open files manually for 30 minutes

**gdep answers all of this in under 0.5 seconds.**

### Measured Performance

| Metric | Result | Notes |
|--------|--------|-------|
| UE5 warm scan | **0.46 s** | 2,800+ asset project |
| Unity warm scan | **0.49 s** | SSD, 900+ classes |
| Peak memory | **28.5 MB** | 10× headroom vs target |
| MCP accuracy | **5 / 5 (100%)** | Code-based facts |

> Full details → [docs/BENCHMARK.md](./docs/BENCHMARK.md) · [docs/mcp-benchmark.md](./docs/mcp-benchmark.md)

---

## 🤖 MCP Integration — Make AI Read Real Code

gdep ships an MCP server for Claude Desktop, Cursor, and any MCP-compatible agent.

### Install in 1 line

```bash
npm install -g gdep-mcp
```

### Configure your agent (copy-paste)

```json
{
  "mcpServers": {
    "gdep": {
      "command": "gdep-mcp",
      "env": { "PYTHONUTF8": "1" }
    }
  }
}
```

That's it. Your AI now has **19** game-engine-aware tools available on every conversation.

### What changes with MCP

```
Without gdep:  "CombatCore probably has some Manager dependencies..." ← hallucination
With gdep:     Direct deps: 2 · Indirect: 200+ UI classes · Asset: prefabs/UI/combat.prefab
```

### 19 MCP Tools at a glance

| Tool | When to use |
|------|-------------|
| `get_project_context` | **Always call first** — full project overview |
| `analyze_impact_and_risk` | Before modifying any class (`detail_level="summary"` for quick count) |
| `explain_method_logic` | Internal control flow of a single method — Guard/Branch/Loop/Always |
| `trace_gameplay_flow` | Trace C++ → Blueprint call chains |
| `inspect_architectural_health` | Tech debt audit |
| `explore_class_semantics` | Unfamiliar class deep-dive |
| `suggest_test_scope` | Which test files to run after modifying a class |
| `suggest_lint_fixes` | Lint issues with code fix suggestions (dry-run) |
| `summarize_project_diff` | Architecture-level summary of a git diff |
| `get_architecture_advice` | Full project diagnosis + LLM-powered advice |
| `execute_gdep_cli` | Raw access to all CLI features |
| `find_unity_event_bindings` | Inspector-wired methods (invisible in code search) |
| `analyze_unity_animator` | Animator state machine structure |
| `analyze_axmol_events` | Axmol EventDispatcher/Scheduler binding map |
| `analyze_ue5_gas` | GAS Abilities / Effects / Tags / ASC — with **confidence header** + IS-A asset role breakdown |
| `analyze_ue5_behavior_tree` | BehaviorTree asset structure |
| `analyze_ue5_state_tree` | StateTree asset structure |
| `analyze_ue5_animation` | ABP states + Montage + GAS Notifies |
| `analyze_ue5_blueprint_mapping` | C++ class → Blueprint impl mapping — with **confidence header** |

### UE5 Confidence Transparency

Every `analyze_ue5_gas` and `analyze_ue5_blueprint_mapping` response starts with:

```
> Analysis method: cpp_source_regex + binary_pattern_match
> Confidence: **MEDIUM**
> Coverage: 4633/4633 assets parsed (100.0%)
> UE version: 5.6 (validated)
```

`gdep init` generates a `.gdep/AGENTS.md` that tells AI agents exactly when to trust gdep results (HIGH = trust fully, MEDIUM = reliable, LOW = verify source) and when to read source files directly.

> Full MCP setup → [gdep-cli/gdep_mcp/README.md](./gdep-cli/gdep_mcp/README.md)

---

## 📦 Installation

**Prerequisites**

| Item | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | CLI · MCP server |
| .NET Runtime | 8.0+ | C# / Unity project analysis |

### One-click (Recommended)

```bash
# Windows
install.bat

# macOS / Linux
chmod +x install.sh && ./install.sh
```

### Manual

```bash
cd gdep-cli && pip install -e .
```

---

## 🚀 Quick Start

```bash
gdep detect {path}                          # auto-detect engine
gdep scan {path} --circular --top 15        # structure overview
gdep init {path}                            # create .gdep/AGENTS.md for AI agents
gdep advise {path}                          # architecture diagnosis + advice
```

After `gdep init`, Claude / Cursor / Gemini automatically read the project context and
know which gdep tools to call for which questions.

---

## 🖥️ Web UI — Visual Analysis in Your Browser

gdep ships a browser UI for interactive, visual analysis — no terminal required after setup.

**Step 1 — Install** (run once from project root)

```
install.bat          # Windows
./install.sh         # macOS / Linux
```

**Step 2 — Launch**

```
run.bat              # Windows — opens backend + frontend in two separate terminals automatically
./run.sh             # macOS/Linux — Terminal 1: backend  (http://localhost:8000)
./run_front.sh       # macOS/Linux — Terminal 2: frontend (http://localhost:5173)
```

Open `http://localhost:5173` → point the sidebar to your project's source folder.

What you get:
- Interactive dependency graphs and call-flow visualization
- Class browser with impact analysis and lint
- AI chat agent that reads your actual codebase (tool-calling)
- Engine-specific explorers: GAS · Blueprint mapping · Animator · BehaviorTree · StateTree

> UI language: **English and Korean only** · Local LLM: **Ollama** supported · Non-commercial, features may not be perfect

Full documentation → [gdep-cli/web/README.md](./gdep-cli/web/README.md)

---

## 🎯 Command Reference

| Command | Summary | When to Use |
|---------|---------|-------------|
| `detect` | Auto-detect engine type | Before first analysis |
| `scan` | Coupling · Cycles · Dead code | Understand structure, before refactor |
| `describe` | Class detail + Blueprint impl + AI summary | Unfamiliar class, code review |
| `flow` | Method call chain (C++→BP boundary) | Bug tracing, flow analysis |
| `impact` | Change impact reverse-trace | Safety check before refactoring |
| `test-scope` | Test files to run after modifying a class | Before merging, CI planning |
| `watch` | Live file-change monitor (impact+test+lint) | During active development |
| `lint` | Game-specific anti-pattern scan (+ `--fix`) | Quality check before PR |
| `advise` | Full architecture diagnosis + LLM advice | Architecture review, tech debt |
| `graph` | Dependency graph export | Documentation, visualization |
| `diff` | Dependency diff before/after commit | PR review, CI gate |
| `init` | Create AI Agent context file | **AI coding assistant setup** |
| `context` | Print project context | Copy-paste to AI chat |
| `hints` | Manage singleton hints | Improve flow accuracy |
| `config` | LLM configuration | Before using AI summary features |


## 📖 Command Details

### scan

```bash
gdep scan {path} [options]
```

| Option | Description |
|--------|-------------|
| `--circular` | Detect circular dependencies |
| `--dead-code` | Detect unreferenced classes |
| `--deep` | Deep analysis including method bodies |
| `--include-refs` | Include Prefab/Blueprint back-references |
| `--top N` | Show top N by coupling (default: 20) |
| `--format json` | JSON output (for CI/Agent) |

### flow — traces C++ → Blueprint boundaries

```bash
gdep flow {path} --class <Class> --method <Method> [--depth N]
```

```
└── UARGamePlayAbility_BasicAttack.ActivateAbility
    ├── CommitAbility ○
    ├── BP_GA_BasicAttack_C.K2_ActivateAbility ○ [BP]   ← Blueprint entry
    └── BP_GA_HeavyAttack_C.K2_ActivateAbility ○ [BP]
```

### test-scope — find test files affected by a class change

```bash
gdep test-scope {path} <ClassName>
gdep test-scope {path} <ClassName> --format json   # CI pipeline output
gdep test-scope {path} <ClassName> --depth 5       # broader search
```

### watch — live monitor for file changes

```bash
gdep watch {path}                        # watch whole project
gdep watch {path} --class CombatManager  # only watch files related to class
gdep watch {path} --debounce 2.0         # adjust debounce (seconds)
```

On every save, instantly prints: impact count · test file count · lint warnings.

### advise — architecture diagnosis

```bash
gdep advise {path}                        # full project diagnosis
gdep advise {path} --focus CombatManager  # class-focused diagnosis
gdep advise {path} --format json          # CI/MCP output
```

Without LLM configured: structured data report (cycles/coupling/dead-code/lint).
With LLM configured: IMMEDIATE / MID-TERM / LONG-TERM natural-language advice.

### lint — 16 game-engine anti-pattern rules

```bash
gdep lint {path}                # scan
gdep lint {path} --fix          # scan + code fix suggestions (dry-run, no file changes)
```

| Rule ID | Engine | Description |
|---------|--------|-------------|
| `UNI-PERF-001` | Unity | GetComponent/Find in Update |
| `UNI-PERF-002` | Unity | new/Instantiate in Update |
| `UNI-ASYNC-001` | Unity | Coroutine while(true) without yield |
| `UNI-ASYNC-002` | Unity | FindObjectOfType/Resources.Load in Coroutine |
| `UE5-PERF-001` | UE5 | SpawnActor/LoadObject in Tick |
| `UE5-PERF-002` | UE5 | Synchronous LoadObject in BeginPlay |
| `UE5-BASE-001` | UE5 | Missing Super:: call |
| `UE5-GAS-001` | UE5 | Missing CommitAbility() in ActivateAbility() |
| `UE5-GAS-002` | UE5 | Expensive world queries in GAS Ability |
| `UE5-GAS-003` | UE5 | Excessive BlueprintCallable (>10) |
| `UE5-GAS-004` | UE5 | Missing const on BlueprintPure method |
| `UE5-NET-001` | UE5 | Replicated property without ReplicatedUsing callback |
| `AXM-PERF-001` | Axmol | getChildByName/Tag in update() |
| `AXM-MEM-001` | Axmol | retain() without release() |
| `AXM-EVENT-001` | Axmol | addEventListenerWith* without removeEventListener |
| `GEN-ARCH-001` | Common | Circular dependency |

---

## 🎮 Supported Engines

| Engine | Class Analysis | Flow Analysis | Back-refs | Specialized |
|--------|---------------|---------------|-----------|-------------|
| Unity (C#) | ✅ | ✅ | ✅ Prefab/Scene | UnityEvent, Animator |
| Unreal Engine 5 | ✅ UCLASS/USTRUCT/UENUM | ✅ C++→BP | ✅ Blueprint/Map | GAS, BP mapping, BT/ST, ABP/Montage |
| Axmol / Cocos2d-x (C++) | ✅ Tree-sitter | ✅ | — | EventDispatcher/Scheduler bindings |
| .NET (C#) | ✅ | ✅ | — | |
| Generic C++ | ✅ | ✅ | — | |

---

## 🔄 Representative Workflows

### Onboarding an unfamiliar codebase

```bash
gdep init {path}
gdep scan {path} --circular --top 20
gdep describe {path} CombatManager --summarize
gdep flow {path} --class CombatManager --method ExecuteAction
```

### UE5 GAS end-to-end

```bash
gdep describe {path} UARGameplayAbility_Dash
gdep flow {path} --class UARGameplayAbility_Dash --method ActivateAbility
```

### Pre-refactor safety check

```bash
gdep impact {path} CombatCore --depth 5
gdep test-scope {path} CombatCore
gdep lint {path} --fix
gdep diff {path} --commit HEAD
```

### Architecture review

```bash
gdep advise {path}
gdep advise {path} --focus BattleManager
```

### CI quality gate

```bash
gdep diff . --commit HEAD~1 --fail-on-cycles
gdep lint . --format json > lint_report.json
gdep test-scope . ChangedClass --format json > test_scope.json
```

### Active development (live feedback)

```bash
gdep watch {path} --class CombatManager
# → On every save: impact count · test files · lint warnings
```

---

## ⚙️ C# Parser (`gdep.dll`)

Ships as an **OS-agnostic single DLL** — identical behavior on Windows · macOS · Linux.

```bash
dotnet publish -c Release --no-self-contained -o publish_dll
```

Detection priority: `$GDEP_DLL` env → `publish_dll/gdep.dll` → `publish/gdep.dll` → legacy binary

---

*MCP Server → [gdep-cli/gdep_mcp/README.md](./gdep-cli/gdep_mcp/README.md)*
*CI/CD Integration → [docs/ci-integration.md](./docs/ci-integration.md)*
*Performance Benchmark → [docs/BENCHMARK.md](./docs/BENCHMARK.md)*
*MCP Token & Accuracy → [docs/mcp-benchmark.md](./docs/mcp-benchmark.md)*
