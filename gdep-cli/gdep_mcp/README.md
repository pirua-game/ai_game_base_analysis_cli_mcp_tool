# gdep-mcp — MCP Server for Game Codebase Analysis

MCP server that lets Claude Desktop, Cursor, and other AI agents analyze game projects
(Unity, Unreal Engine 5, C++, C#) using [gdep](https://github.com/pirua-game/gdep).

**Read this in other languages:**
[한국어](./README_KR.md) · [日本語](./README_JA.md) · [简体中文](./README_ZH.md) · [繁體中文](./README_ZH_TW.md)

---

## ⚡ Quick Install

### via npm (Recommended — no git clone required)

```bash
npm install -g gdep-mcp
```

This automatically installs `gdep` and `mcp[cli]` Python packages as well.

Then add to your AI agent config:

```json
{
  "mcpServers": {
    "gdep": {
      "command": "gdep-mcp"
    }
  }
}
```

> Each tool accepts `project_path` as a parameter. No project path needed in the config.

### via pip (Manual)

```bash
pip install gdep "mcp[cli]"
```

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "gdep": {
      "command": "/path/to/gdep-cli/.venv/bin/python",
      "args": ["/path/to/gdep-cli/gdep_mcp/server.py"],
      "cwd": "/path/to/gdep-cli"
    }
  }
}
```

> **Windows example:**
> `"command": "C:/Users/YourName/gdep/gdep-cli/.venv/Scripts/python.exe"`

---

## 🛠 Available Tools (19)

### Context Tool — call first at session start

| Tool | Description |
|------|-------------|
| `get_project_context` | Full project overview. Reads `.gdep/AGENTS.md` if present, otherwise generates on-the-fly |

### High-level Intent Tools (9)

| Tool | Description |
|------|-------------|
| `analyze_impact_and_risk` | Impact scope + lint before modifying a class or method. `method_name=` for method-level callers; `detail_level="summary"` for a quick count; `query=` to filter results |
| `explain_method_logic` | Summarize internal control flow of a single method — Guard / Branch / Loop / Always in 5–10 lines. Supports C++ namespace-style functions |
| `trace_gameplay_flow` | Method call chain + source code |
| `inspect_architectural_health` | Coupling / circular deps / dead code / anti-patterns |
| `explore_class_semantics` | Class structure + AI 3-line summary |
| `suggest_test_scope` | Test files to run after modifying a class (pattern-based, CI-ready JSON output) |
| `suggest_lint_fixes` | Lint issues with concrete code fix suggestions (dry-run, no file changes) |
| `summarize_project_diff` | Architecture-level summary of a git diff — new cycles, high-coupling changes |
| `get_architecture_advice` | Full project scan + lint + impact → structured report or LLM-powered advice |

### Raw CLI Access (1)

| Tool | Description |
|------|-------------|
| `execute_gdep_cli` | `args: list[str]` — Direct access to all gdep CLI features |

### Axmol / Cocos2d-x Tools (1)

| Tool | Description |
|------|-------------|
| `analyze_axmol_events` | EventDispatcher/Scheduler binding map — who registers and handles which events |

### Unity Tools (2)

| Tool | Description |
|------|-------------|
| `find_unity_event_bindings` | Detect Inspector-bound methods in .prefab/.unity/.asset |
| `analyze_unity_animator` | .controller (Unity YAML) → Layer/State/BlendTree structure |

### UE5 Tools (5)

| Tool | Description |
|------|-------------|
| `analyze_ue5_gas` | GA/GE/AS classes + GameplayTag extraction + ASC usage. Returns **confidence header** (method / tier / coverage / UE version) + IS-A asset role breakdown (GA / GE / AS / ABP vs referencer). Tag noise filtered (GUID segments rejected). Enum class false-positive fixed. |
| `analyze_ue5_behavior_tree` | BT_* .uasset → Task/Decorator/Service/Blackboard |
| `analyze_ue5_state_tree` | ST_* .uasset → Task/AIController connections |
| `analyze_ue5_animation` | ABP state machine + Montage sections/slots/GAS Notify |
| `analyze_ue5_blueprint_mapping` | C++ class → BP implementation mapping (K2 overrides/variables/GAS tags). Returns **confidence header** with coverage and UE version. |

---

## 💬 Usage Examples with AI

```
"What classes are affected if I modify BattleCore?"
→ analyze_impact_and_risk

"Quick — how many classes use BattleCore?"
→ analyze_impact_and_risk(path, "BattleCore", detail_level="summary")

"Who calls BattleCore.ExecuteAction across the whole project?"
→ analyze_impact_and_risk(path, "BattleCore", method_name="ExecuteAction")

"What conditions are inside the DrawCard method?"
→ explain_method_logic

"How does the PlayHand method actually work?"
→ trace_gameplay_flow

"What's the tech debt level of this project?"
→ inspect_architectural_health

"Which tests should I run after changing BattleCore?"
→ suggest_test_scope

"How to fix the lint warnings in BattleManager?"
→ suggest_lint_fixes

"Summarize what changed in this PR architecturally"
→ summarize_project_diff

"What should I fix first in this codebase?"
→ get_architecture_advice

"Who handles the jump event in this Axmol project?"
→ analyze_axmol_events

"How many GAS abilities are there? What are the Blueprint implementations?"
→ analyze_ue5_gas + analyze_ue5_blueprint_mapping

"Find the Blueprint that inherits ARGameplayAbility_Dash"
→ analyze_ue5_blueprint_mapping(path, "ARGameplayAbility_Dash")
```

---

## 🔍 UE5 Confidence-Transparent Output

Both `analyze_ue5_gas` and `analyze_ue5_blueprint_mapping` prefix every response with a confidence header:

```
> Analysis method: cpp_source_regex + binary_pattern_match
> Confidence: **MEDIUM**
> Coverage: 4633/4633 assets parsed (100.0%)
> UE version: 5.6 (validated)
```

| Tier | Source | Guidance |
|------|--------|----------|
| **HIGH** | C++ source regex | Trust without additional verification |
| **MEDIUM** | Binary NativeParentClass + cross-reference | Reliable; cross-check source before architecture decisions |
| **LOW** | Filename heuristics / LFS stubs > 50% | Use as index only; read source files before making changes |

`analyze_ue5_gas` also reports IS-A asset roles vs. mere referencers:
```
## Asset Roles
  IS-A GA  (GA_*):  7
  IS-A GE  (GE_*):  8
  IS-A ABP (ABP_*): 3
  References only:  14
```

`gdep init` generates a `.gdep/AGENTS.md` that guides AI agents on when to trust gdep results and when to cross-check source files directly.

---

## 📋 Prerequisites

| Item | Version |
|------|---------|
| Python | 3.11+ |
| .NET Runtime | 8.0+ (for C#/Unity analysis) |
| Node.js | 18+ (for npm install method only) |

---

## 🔗 Links

- [Main Repository](https://github.com/pirua-game/gdep)
- [Full CLI Documentation](https://github.com/pirua-game/gdep/blob/main/README.md)
- [Performance Benchmark](https://github.com/pirua-game/gdep/blob/main/docs/BENCHMARK.md)
- [CI/CD Integration](https://github.com/pirua-game/gdep/blob/main/docs/ci-integration.md)
