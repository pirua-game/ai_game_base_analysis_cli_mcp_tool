# 🎮 gdep — Game Codebase Analysis Tool

Analyze game client codebases directly from your **terminal and AI Agent**.

Supports Unity · Cocos2d-x · Unreal Engine 5 · .NET C# · Generic C++.

[![CI](https://github.com/pirua-game/gdep/actions/workflows/ci.yml/badge.svg)](https://github.com/pirua-game/gdep/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/gdep)](https://pypi.org/project/gdep/)

**[GitHub](https://github.com/pirua-game/gdep)** ·
**[MCP Setup](https://github.com/pirua-game/gdep/blob/main/gdep-cli/gdep_mcp/README.md)** ·
**[CI/CD Integration](https://github.com/pirua-game/gdep/blob/main/docs/ci-integration.md)**

**Read this in other languages:**
[한국어](https://github.com/pirua-game/gdep/blob/main/README_KR.md) ·
[日本語](https://github.com/pirua-game/gdep/blob/main/README_JA.md) ·
[简体中文](https://github.com/pirua-game/gdep/blob/main/README_ZH.md) ·
[繁體中文](https://github.com/pirua-game/gdep/blob/main/README_ZH_TW.md)

---

## 📦 Installation

**Prerequisites**

| Item | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | CLI · MCP server |
| .NET Runtime | 8.0+ | C# / Unity project analysis |

```bash
pip install gdep
```

After installation, the `gdep` command is available globally.

> For the MCP server (Claude Desktop / Cursor integration), also install:
> ```bash
> npm install -g gdep-mcp
> ```

---

## 🚀 Quick Start

### 1. Detect Project

```bash
gdep detect {path}
```

### 2. Analyze Structure

```bash
gdep scan {path} --circular --top 15
```

```
┌─ scan results ───────────────────────────────────────┐
│ Files: 312  |  Classes: 847  |  Dead Code: 12        │
└──────────────────────────────────────────────────────┘
── Top Classes by Coupling
  1  CombatManager   23
  2  DataManager     18
── Circular Dependencies
  ↻ CombatCore → CombatUnit → CombatCore
```

### 3. Initialize AI Agent Context

```bash
# Creates .gdep/AGENTS.md — auto-read by Claude / Cursor / Gemini
gdep init {path}
```

---

## 🎯 Command Reference

| Command | Summary | When to Use |
|---------|---------|-------------|
| `detect` | Auto-detect engine type | Before first analysis |
| `scan` | Coupling · Cycles · Dead code | Understand structure, before refactor |
| `describe` | Class detail + **full inheritance chain** + Blueprint impl + AI summary | Unfamiliar class, code review |
| `flow` | Method call chain trace (C++→BP boundary) | Bug tracing, flow analysis |
| `impact` | Change impact reverse-trace | Safety check before refactoring |
| `lint` | Game-specific anti-pattern scan | Quality check before PR |
| `graph` | Dependency graph export | Documentation, visualization |
| `diff` | Dependency diff before/after git commit | PR review, CI gate |
| `init` | Create AI Agent context | **First AI coding assistant setup** |
| `context` | Print project context | Copy-paste to AI chat |
| `hints` | Manage singleton hints | Improve flow accuracy |
| `config` | LLM configuration | Before using AI summary features |

---

## 🤝 AI Agent + MCP Integration

gdep provides an MCP server for direct use in Claude Desktop, Cursor, and other MCP-compatible AI agents.

### Quick Install via npm (Recommended)

```bash
npm install -g gdep-mcp
```

Claude Desktop config (`claude_desktop_config.json`):

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

### MCP Tools (13)

| Tool | Scenario |
|------|----------|
| `get_project_context` | **Call first** — full project overview |
| `analyze_impact_and_risk` | Safety check before modifying a class |
| `trace_gameplay_flow` | Trace how a feature works (C++→BP) |
| `inspect_architectural_health` | Full tech debt diagnosis |
| `explore_class_semantics` | Understand an unfamiliar class |
| `execute_gdep_cli` | Raw access to all CLI features |
| `find_unity_event_bindings` | Unity Inspector event bindings |
| `analyze_unity_animator` | Unity Animator state machine |
| `analyze_ue5_gas` | UE5 GAS system full analysis — confidence header + IS-A asset role breakdown |
| `analyze_ue5_behavior_tree` | UE5 BehaviorTree structure |
| `analyze_ue5_state_tree` | UE5 StateTree structure |
| `analyze_ue5_animation` | UE5 ABP + Montage analysis |
| `analyze_ue5_blueprint_mapping` | C++ class → Blueprint impl mapping — confidence header |

---

## 🎮 Supported Engines

| Engine | Class Analysis | Flow Analysis | Back-refs | Specialized |
|--------|---------------|---------------|-----------|-------------|
| Unity (C#) | ✅ | ✅ | ✅ Prefab/Scene | UnityEvent, Animator |
| Unreal Engine 5 | ✅ UCLASS/USTRUCT/UENUM | ✅ C++→BP | ✅ Blueprint/Map | GAS, BP mapping, BT/ST, ABP/Montage |
| Cocos2d-x (C++) | ✅ | ✅ | - | - |
| .NET (C#) | ✅ | ✅ | - | - |
| Generic C++ | ✅ | ✅ | - | - |

---

## 📋 Lint Rules

| Rule ID | Engine | Description |
|---------|--------|-------------|
| `UNI-PERF-001` | Unity | GetComponent/Find in Update |
| `UNI-PERF-002` | Unity | new/Instantiate allocation in Update |
| `UNI-ASYNC-001` | Unity | Coroutine while(true) without yield |
| `UNI-ASYNC-002` | Unity | FindObjectOfType/Resources.Load inside Coroutine |
| `UE5-PERF-001` | UE5 | SpawnActor/LoadObject in Tick |
| `UE5-PERF-002` | UE5 | Synchronous LoadObject in BeginPlay |
| `UE5-BASE-001` | UE5 | Missing Super:: call |
| `UE5-GAS-001` | UE5 | Missing CommitAbility() in ActivateAbility() |
| `UE5-GAS-002` | UE5 | Expensive queries in GAS Ability |
| `UE5-GAS-003` | UE5 | Excessive BlueprintCallable (>10) |
| `UE5-GAS-004` | UE5 | Missing const on BlueprintPure method |
| `UE5-NET-001` | UE5 | Replicated property without callback |
| `GEN-ARCH-001` | Common | Circular dependency |

---

## ⚙️ C# Parser (`gdep.dll`)

The C# parser ships as an **OS-agnostic single DLL**, running identically on Windows · macOS · Linux.

Detection priority: `$GDEP_DLL` env → `publish_dll/gdep.dll` → `publish/gdep.dll` → legacy binary

---

## 📚 More

- [Full README & Workflows](https://github.com/pirua-game/gdep)
- [MCP Server Setup](https://github.com/pirua-game/gdep/blob/main/gdep-cli/gdep_mcp/README.md)
- [CI/CD Integration](https://github.com/pirua-game/gdep/blob/main/docs/ci-integration.md)
- [Performance Benchmark](https://github.com/pirua-game/gdep/blob/main/docs/BENCHMARK.md)
