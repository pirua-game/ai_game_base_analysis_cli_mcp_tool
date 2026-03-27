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
      "args": ["/path/to/gdep-cli/gdep_mcp/server.py"],
      "cwd": "/path/to/gdep-cli"
    }
  }
}
```

---

## 🛠 工具清單（19 個）

### 上下文工具

| 工具 | 說明 |
|------|------|
| `get_project_context` | **工作階段開始時首先呼叫** — 專案整體概覽 |

### 高層意圖工具（9 個）

| 工具 | 說明 |
|------|------|
| `analyze_impact_and_risk` | 修改類別或方法前的影響範圍 + 程式碼檢查。`method_name=` 追蹤方法級呼叫方；`detail_level="summary"` 快速摘要；`query=` 篩選結果 |
| `explain_method_logic` | 單一方法內部控制流摘要 — Guard/Branch/Loop/Always 5~10 行。支援 C++ namespace 函式 |
| `trace_gameplay_flow` | 方法呼叫鏈追蹤 + 原始碼 |
| `inspect_architectural_health` | 耦合度/循環引用/死碼/反模式 |
| `explore_class_semantics` | 類別結構 + AI 三行摘要 |
| `suggest_test_scope` | 修改類別後需執行的測試檔案自動推算（支援 CI JSON 輸出） |
| `suggest_lint_fixes` | lint 問題 + 程式碼修復建議（dry-run，不修改檔案） |
| `summarize_project_diff` | 從架構角度彙總 git diff — 循環引用增減、高耦合警告 |
| `get_architecture_advice` | scan+lint+impact 綜合 → 結構化報告或 LLM 架構建議 |

### Raw CLI 存取

| 工具 | 說明 |
|------|------|
| `execute_gdep_cli` | 直接存取所有 gdep CLI 功能 |

### Axmol / Cocos2d-x 專用

| 工具 | 說明 |
|------|------|
| `analyze_axmol_events` | EventDispatcher/Scheduler 綁定映射 — 事件註冊/處理主體提取 |

### Unity 專用

| 工具 | 說明 |
|------|------|
| `find_unity_event_bindings` | Unity Inspector 綁定方法檢測 |
| `analyze_unity_animator` | .controller → Layer/State/BlendTree 結構 |

### UE5 專用

| 工具 | 說明 |
|------|------|
| `analyze_ue5_gas` | GA/GE/AS 類別 + GameplayTag + ASC 使用處。包含**信賴度標頭**（分析方法/信賴等級/覆蓋率/UE版本）+ IS-A 資產角色分類（GA/GE/AS/ABP vs 僅參照）。過濾 GUID 雜訊標籤。已修正 `enum class` 誤報。 |
| `analyze_ue5_behavior_tree` | BT_* .uasset → Task/Decorator/Service |
| `analyze_ue5_state_tree` | ST_* .uasset → Task/AIController 連結 |
| `analyze_ue5_animation` | ABP 狀態機 + Montage 分段/插槽/GAS Notify |
| `analyze_ue5_blueprint_mapping` | C++ 類別 → Blueprint 實作對應。包含**信賴度標頭**（覆蓋率 + UE版本）。 |

---

## 🔍 UE5 信賴度透明化輸出

`analyze_ue5_gas` 和 `analyze_ue5_blueprint_mapping` 在每個回應頂部輸出信賴度標頭：

```
> Analysis method: cpp_source_regex + binary_pattern_match
> Confidence: **MEDIUM**
> Coverage: 4633/4633 assets parsed (100.0%)
> UE version: 5.6 (validated)
```

| 等級 | 依據 | 建議 |
|------|------|------|
| **HIGH** | C++ 原始碼直接解析 | 無需額外驗證即可信任 |
| **MEDIUM** | 二進位 NativeParentClass + 交叉引用 | 大多數情況可信；架構決策前建議交叉核實原始碼 |
| **LOW** | 檔案名稱啟發式 / LFS 存根超過 50% | 僅作索引使用；變更前直接讀取原始檔案 |

`gdep init` 產生的 `.gdep/AGENTS.md` 包含各 Confidence 等級對應的 AI Agent 行為指南。

---

*[主要儲存庫](https://github.com/pirua-game/gdep)*
