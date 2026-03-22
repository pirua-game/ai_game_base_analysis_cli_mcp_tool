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
      "args": ["/path/to/gdep-cli/gdep-mcp/server.py"],
      "cwd": "/path/to/gdep-cli"
    }
  }
}
```

> **Windows example:**
> `"command": "C:/Users/YourName/gdep/gdep-cli/.venv/Scripts/python.exe"`

---

## 🛠 Available Tools (13)

### Context Tool — call first at session start

| Tool | Description |
|------|-------------|
| `get_project_context` | Full project overview. Reads `.gdep/AGENTS.md` if present, otherwise generates on-the-fly |

### High-level Intent Tools (4)

| Tool | Description |
|------|-------------|
| `analyze_impact_and_risk` | Impact scope + lint before modifying a class |
| `trace_gameplay_flow` | Method call chain + source code |
| `inspect_architectural_health` | Coupling / circular deps / dead code / anti-patterns |
| `explore_class_semantics` | Class structure + AI 3-line summary |

### Raw CLI Access (1)

| Tool | Description |
|------|-------------|
| `execute_gdep_cli` | `args: list[str]` — Direct access to all gdep CLI features |

### Unity Tools (2)

| Tool | Description |
|------|-------------|
| `find_unity_event_bindings` | Detect Inspector-bound methods in .prefab/.unity/.asset |
| `analyze_unity_animator` | .controller (Unity YAML) → Layer/State/BlendTree structure |

### UE5 Tools (5)

| Tool | Description |
|------|-------------|
| `analyze_ue5_gas` | GA/GE/AS classes + GameplayTag extraction + ASC usage |
| `analyze_ue5_behavior_tree` | BT_* .uasset → Task/Decorator/Service/Blackboard |
| `analyze_ue5_state_tree` | ST_* .uasset → Task/AIController connections |
| `analyze_ue5_animation` | ABP state machine + Montage sections/slots/GAS Notify |
| `analyze_ue5_blueprint_mapping` | C++ class → BP implementation mapping (K2 overrides/variables/GAS tags) |

---

## 💬 Usage Examples with AI

```
"What classes are affected if I modify CombatCore?"
→ analyze_impact_and_risk

"How does the ExecuteAction method actually work?"
→ trace_gameplay_flow

"What's the tech debt level of this project?"
→ inspect_architectural_health

"How many GAS abilities are there? What are the Blueprint implementations?"
→ analyze_ue5_gas + analyze_ue5_blueprint_mapping

"Find the Blueprint that inherits ARGameplayAbility_Dash"
→ analyze_ue5_blueprint_mapping(path, "ARGameplayAbility_Dash")
```

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
