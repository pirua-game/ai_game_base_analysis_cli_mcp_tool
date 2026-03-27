# gdep-mcp — 游戏代码库分析 MCP 服务器

让 Claude Desktop、Cursor 等 AI Agent 通过 [gdep](https://github.com/pirua-game/gdep)
分析游戏项目（Unity、UE5、C++、C#）的 MCP 服务器。

**其他语言版本：**
[English](./README.md) · [한국어](./README_KR.md) · [日本語](./README_JA.md) · [繁體中文](./README_ZH_TW.md)

---

## ⚡ 快速安装

### 通过 npm 安装（推荐 — 无需 git clone）

```bash
npm install -g gdep-mcp
```

自动同时安装 `gdep` 和 `mcp[cli]` Python 包。

在 AI Agent 配置中添加：

```json
{
  "mcpServers": {
    "gdep": {
      "command": "gdep-mcp"
    }
  }
}
```

> 每次工具调用时通过参数传入 `project_path`，无需在配置中指定项目路径。

### 通过 pip 手动安装

```bash
pip install gdep "mcp[cli]"
```

**Claude Desktop 配置** (`claude_desktop_config.json`)：

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

---

## 🛠 工具列表（19个）

### 上下文工具

| 工具 | 说明 |
|------|------|
| `get_project_context` | **会话开始时首先调用** — 项目整体概览 |

### 高层意图工具（9个）

| 工具 | 说明 |
|------|------|
| `analyze_impact_and_risk` | 修改类或方法前的影响范围 + 代码检查。`method_name=` 追踪方法级调用方；`detail_level="summary"` 快速摘要；`query=` 过滤结果 |
| `explain_method_logic` | 单个方法内部控制流摘要 — Guard/Branch/Loop/Always 5~10 行。支持 C++ namespace 函数 |
| `trace_gameplay_flow` | 方法调用链追踪 + 源代码 |
| `inspect_architectural_health` | 耦合度/循环引用/死代码/反模式 |
| `explore_class_semantics` | 类结构 + AI 三行摘要 |
| `suggest_test_scope` | 修改类后需运行的测试文件自动推算（支持 CI JSON 输出） |
| `suggest_lint_fixes` | lint 问题 + 代码修复建议（dry-run，不修改文件） |
| `summarize_project_diff` | 从架构角度汇总 git diff — 循环引用增减、高耦合警告 |
| `get_architecture_advice` | scan+lint+impact 综合 → 结构化报告或 LLM 架构建议 |

### Raw CLI 访问

| 工具 | 说明 |
|------|------|
| `execute_gdep_cli` | 直接访问所有 gdep CLI 功能 |

### Axmol / Cocos2d-x 专用

| 工具 | 说明 |
|------|------|
| `analyze_axmol_events` | EventDispatcher/Scheduler 绑定映射 — 事件注册/处理主体提取 |

### Unity 专用

| 工具 | 说明 |
|------|------|
| `find_unity_event_bindings` | Unity Inspector 绑定方法检测 |
| `analyze_unity_animator` | .controller → Layer/State/BlendTree 结构 |

### UE5 专用

| 工具 | 说明 |
|------|------|
| `analyze_ue5_gas` | GA/GE/AS 类 + GameplayTag + ASC 使用处。包含**置信度标头**（分析方法/置信等级/覆盖率/UE版本）+ IS-A 资产角色分类（GA/GE/AS/ABP vs 仅引用）。过滤 GUID 噪声标签。已修复 `enum class` 误报。 |
| `analyze_ue5_behavior_tree` | BT_* .uasset → Task/Decorator/Service |
| `analyze_ue5_state_tree` | ST_* .uasset → Task/AIController 连接 |
| `analyze_ue5_animation` | ABP 状态机 + Montage 分段/插槽/GAS Notify |
| `analyze_ue5_blueprint_mapping` | C++ 类 → Blueprint 实现映射。包含**置信度标头**（覆盖率 + UE版本）。 |

---

## 🔍 UE5 置信度透明化输出

`analyze_ue5_gas` 和 `analyze_ue5_blueprint_mapping` 在每个响应的顶部输出置信度标头：

```
> Analysis method: cpp_source_regex + binary_pattern_match
> Confidence: **MEDIUM**
> Coverage: 4633/4633 assets parsed (100.0%)
> UE version: 5.6 (validated)
```

| 等级 | 依据 | 建议 |
|------|------|------|
| **HIGH** | C++ 源码直接解析 | 无需额外验证即可信任 |
| **MEDIUM** | 二进制 NativeParentClass + 交叉引用 | 大多数情况可信；架构决策前建议交叉核实源码 |
| **LOW** | 文件名启发式 / LFS 存根超过 50% | 仅作索引使用；变更前直接读取源文件 |

`gdep init` 生成的 `.gdep/AGENTS.md` 包含各 Confidence 等级对应的 AI Agent 行为指南。

---

*[主仓库](https://github.com/pirua-game/gdep)*
