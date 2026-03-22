# gdep-mcp — 遊戲程式碼庫分析 MCP 伺服器

讓 Claude Desktop、Cursor 等 AI Agent 透過 [gdep](https://github.com/pirua-game/gdep)
分析遊戲專案（Unity、UE5、C++、C#）的 MCP 伺服器。

**其他語言版本：**
[English](./README.md) · [한국어](./README_KR.md) · [日本語](./README_JA.md) · [简体中文](./README_ZH.md)

---

## ⚡ 快速安裝

### 透過 npm 安裝（推薦 — 無需 git clone）

```bash
npm install -g gdep-mcp
```

自動同時安裝 `gdep` 和 `mcp[cli]` Python 套件。

在 AI Agent 設定中加入：

```json
{
  "mcpServers": {
    "gdep": {
      "command": "gdep-mcp"
    }
  }
}
```

> 每次工具呼叫時透過參數傳入 `project_path`，無需在設定中指定專案路徑。

### 透過 pip 手動安裝

```bash
pip install gdep "mcp[cli]"
```

**Claude Desktop 設定** (`claude_desktop_config.json`)：

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

## 🛠 工具清單（13 個）

| 工具 | 說明 |
|------|------|
| `get_project_context` | **工作階段開始時首先呼叫** — 專案整體概覽 |
| `analyze_impact_and_risk` | 修改類別前的影響範圍 + 程式碼檢查 |
| `trace_gameplay_flow` | 方法呼叫鏈追蹤 + 原始碼 |
| `inspect_architectural_health` | 耦合度/循環引用/死碼/反模式 |
| `explore_class_semantics` | 類別結構 + AI 三行摘要 |
| `execute_gdep_cli` | 直接存取所有 gdep CLI 功能 |
| `find_unity_event_bindings` | Unity Inspector 綁定方法檢測 |
| `analyze_unity_animator` | .controller → Layer/State/BlendTree 結構 |
| `analyze_ue5_gas` | GA/GE/AS 類別 + GameplayTag + ASC 使用處 |
| `analyze_ue5_behavior_tree` | BT_* .uasset → Task/Decorator/Service |
| `analyze_ue5_state_tree` | ST_* .uasset → Task/AIController 連結 |
| `analyze_ue5_animation` | ABP 狀態機 + Montage 分段/插槽/GAS Notify |
| `analyze_ue5_blueprint_mapping` | C++ 類別 → Blueprint 實作對應 |

---

*[主要儲存庫](https://github.com/pirua-game/gdep)*
