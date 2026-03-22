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
      "args": ["/path/to/gdep-cli/gdep-mcp/server.py"],
      "cwd": "/path/to/gdep-cli"
    }
  }
}
```

---

## 🛠 工具列表（13个）

| 工具 | 说明 |
|------|------|
| `get_project_context` | **会话开始时首先调用** — 项目整体概览 |
| `analyze_impact_and_risk` | 修改类前的影响范围 + 代码检查 |
| `trace_gameplay_flow` | 方法调用链追踪 + 源代码 |
| `inspect_architectural_health` | 耦合度/循环引用/死代码/反模式 |
| `explore_class_semantics` | 类结构 + AI 三行摘要 |
| `execute_gdep_cli` | 直接访问所有 gdep CLI 功能 |
| `find_unity_event_bindings` | Unity Inspector 绑定方法检测 |
| `analyze_unity_animator` | .controller → Layer/State/BlendTree 结构 |
| `analyze_ue5_gas` | GA/GE/AS 类 + GameplayTag + ASC 使用处 |
| `analyze_ue5_behavior_tree` | BT_* .uasset → Task/Decorator/Service |
| `analyze_ue5_state_tree` | ST_* .uasset → Task/AIController 连接 |
| `analyze_ue5_animation` | ABP 状态机 + Montage 分段/插槽/GAS Notify |
| `analyze_ue5_blueprint_mapping` | C++ 类 → Blueprint 实现映射 |

---

*[主仓库](https://github.com/pirua-game/gdep)*
