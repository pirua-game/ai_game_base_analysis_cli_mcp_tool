# 🎮 gdep — 遊戲程式碼庫分析工具

**在 0.5 秒內理解 Unity/UE5/Axmol 大型專案，讓 Claude/Cursor 真正讀懂程式碼**

[![CI](https://github.com/pirua-game/gdep/actions/workflows/ci.yml/badge.svg)](https://github.com/pirua-game/gdep/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/gdep)](https://pypi.org/project/gdep/)
[![npm](https://img.shields.io/npm/v/gdep-mcp)](https://www.npmjs.com/package/gdep-mcp)

> *"修改這個類別會影響哪裡？"* — 3 秒精確回答，零幻覺
> 實測：**MCP 準確率 100% (5/5)** — 基於程式碼的事實 vs 普通 Claude 猜測 + 幻覺

**其他語言版本：**
[English](./README.md) · [한국어](./README_KR.md) · [日本語](./README_JA.md) · [简体中文](./README_ZH.md)

---

## ✨ 為什麼要用 gdep？

大型遊戲客戶端令人痛苦：

- UE5 300 個以上 Blueprint → *「這個 Ability 從哪裡被呼叫？」* — 半天時間消失
- Unity 50 個 Manager + Prefab 引用 → 重構時循環相依爆發
- *「修改這個類別會導致什麼崩潰？」* — 手動追蹤 30 分鐘

**gdep 在 0.5 秒內解決這一切。**

### 實測效能指標

| 指標 | 數值 | 備註 |
|------|------|------|
| UE5 熱快取掃描 | **0.46 秒** | 2,800+ uasset 專案 |
| Unity 熱快取掃描 | **0.49 秒** | SSD 環境，900+ 個類別 |
| 峰值記憶體 | **28.5 MB** | 目標 10 倍餘量 |
| MCP 準確率 | **5/5 (100%)** | 基於程式碼的事實 |

> 詳情 → [docs/BENCHMARK_ZH_TW.md](./docs/BENCHMARK_ZH_TW.md) · [docs/mcp-benchmark_ZH_TW.md](./docs/mcp-benchmark_ZH_TW.md)

---

## 🤖 MCP 整合 — 讓 AI 讀懂真實程式碼

gdep 為 Claude Desktop、Cursor 等 MCP 相容 AI Agent 提供 MCP 伺服器。

### 一行安裝

```bash
npm install -g gdep-mcp
```

### Agent 設定（複製貼上）

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

設定完成。Claude · Cursor · Gemini 每次對話都可使用 **19 個**遊戲引擎專屬工具。

### MCP 改變什麼

```
普通 Claude: "CombatCore 可能有一些 Manager 相依性..." ← 猜測
gdep MCP:   直接相依 2 個 · 間接 200+ UI 類別 · 資源: prefabs/UI/combat.prefab
```

### 19 個 MCP 工具一覽

| 工具 | 使用時機 |
|------|---------|
| `get_project_context` | **始終最先呼叫** — 專案整體概覽 |
| `analyze_impact_and_risk` | 修改類別或方法前的安全確認（`method_name=` 追蹤方法級呼叫方；`detail_level="summary"` 快速摘要） |
| `explain_method_logic` | 單一方法內部控制流摘要 — Guard/Branch/Loop/Always。支援 C++ namespace 函式 |
| `trace_gameplay_flow` | C++ → Blueprint 呼叫鏈追蹤 |
| `inspect_architectural_health` | 技術債務全面診斷 |
| `explore_class_semantics` | 陌生類別深度分析 |
| `suggest_test_scope` | 修改類別後需執行的測試檔案自動推算 |
| `suggest_lint_fixes` | lint 問題 + 程式碼修復建議（dry-run） |
| `summarize_project_diff` | 從架構角度彙總 git diff |
| `get_architecture_advice` | 專案綜合診斷 + LLM 架構建議 |
| `execute_gdep_cli` | CLI 全功能直接存取 |
| `find_unity_event_bindings` | Inspector 綁定方法（程式碼搜尋不到的區域） |
| `analyze_unity_animator` | Animator 狀態機結構 |
| `analyze_axmol_events` | Axmol EventDispatcher/Scheduler 綁定映射 |
| `analyze_ue5_gas` | GAS Ability / Effect / Tag / ASC 全量 — 包含**信賴度標頭** + IS-A 資產角色分類 |
| `analyze_ue5_behavior_tree` | BehaviorTree 資源結構 |
| `analyze_ue5_state_tree` | StateTree 資源結構 |
| `analyze_ue5_animation` | ABP 狀態 + Montage + GAS Notify |
| `analyze_ue5_blueprint_mapping` | C++ 類別 → Blueprint 實作對應 — 包含**信賴度標頭** |

### UE5 信賴度透明化

每個 UE5 分析回應的頂部均包含：
```
> Confidence: **MEDIUM** | Coverage: 4633/4633 (100.0%) | UE version: 5.6 (validated)
```
`gdep init` 產生的 `.gdep/AGENTS.md` 提供各信賴等級對應的 AI Agent 行為指南。

> 詳細設定 → [gdep-cli/gdep_mcp/README_ZH_TW.md](./gdep-cli/gdep_mcp/README_ZH_TW.md)

---

## 📦 安裝

| 項目 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | CLI · MCP 伺服器 |
| .NET Runtime | 8.0+ | C# / Unity 專案分析 |

```bash
# Windows
install.bat

# macOS / Linux
chmod +x install.sh && ./install.sh
```

---

## 🚀 快速開始

```bash
gdep detect {path}                     # 自動偵測引擎
gdep scan {path} --circular --top 15   # 結構分析
gdep init {path}                       # 建立 .gdep/AGENTS.md
gdep advise {path}                     # 架構診斷 + 建議
```

---

## 🖥️ Web UI — 在瀏覽器中視覺化分析

安裝完成後無需終端，直接在瀏覽器中查看相依圖、呼叫流程並使用 AI 聊天。

**第一步 — 安裝**（在專案根目錄執行一次）

```
install.bat          # Windows
./install.sh         # macOS / Linux
```

**第二步 — 啟動**

```
run.bat              # Windows — 自動在兩個獨立終端中啟動後端 + 前端
./run.sh             # macOS/Linux — 終端 1：後端  (http://localhost:8000)
./run_front.sh       # macOS/Linux — 終端 2：前端 (http://localhost:5173)
```

開啟 `http://localhost:5173` → 在側邊欄中指定專案原始碼目錄

主要功能：
- 互動式相依圖與呼叫流程視覺化
- 類別瀏覽器（含影響分析與 lint）
- 讀取實際程式碼的 AI 聊天智能體（工具呼叫）
- 引擎專屬探索器：GAS · Blueprint 對應 · Animator · BehaviorTree · StateTree

> UI 語言：**僅支援英語與韓語** · 本機 LLM：支援 **Ollama** · 非商業工具，部分功能可能尚不完善

詳細文件 → [gdep-cli/web/README.md](./gdep-cli/web/README.md)

---

## 🎯 指令參考

| 指令 | 說明 | 使用時機 |
|------|------|---------|
| `detect` | 自動偵測引擎類型 | 首次分析前 |
| `scan` | 耦合度·循環相依·死碼 | 了解結構、重構前 |
| `describe` | 類別詳情 + **完整繼承鏈** + Blueprint 實作 + AI 摘要 | 陌生類別、程式碼審查 |
| `flow` | 呼叫鏈追蹤（C++→BP 邊界） | Bug 追蹤、流程分析 |
| `impact` | 變更影響範圍反向追蹤 | 重構前安全確認 |
| `method-impact` | 反向追蹤呼叫特定方法的所有方法 | 修改方法前了解呼叫來源 |
| `test-scope` | 修改類別後應執行的測試檔案 | 合併前、CI 規劃 |
| `watch` | 即時檔案變更監視 (impact+test+lint) | 開發中持續監控 |
| `lint` | 16 條遊戲專用反模式（+ `--fix`） | PR 前品質檢查 |
| `advise` | 整體架構診斷 + LLM 建議 | 架構審查、技術債務 |
| `graph` | 相依關係圖匯出 | 文件化、視覺化 |
| `diff` | 提交前後相依比對 | PR 審查、CI 閘門 |
| `init` | 建立 AI Agent 內容 | **AI 編碼助手初始設定** |
| `context` | 輸出專案內容 | 複製至 AI 對話 |
| `hints` | 管理單例提示 | 提升 flow 準確度 |
| `config` | LLM 設定 | 使用 AI 摘要前 |

---

## 🎮 支援的引擎

| 引擎 | 類別分析 | 流程分析 | 反向引用 | 專項功能 |
|------|---------|---------|---------|---------|
| Unity (C#) | ✅ | ✅ | ✅ Prefab/Scene | UnityEvent、Animator |
| Unreal Engine 5 | ✅ UCLASS/USTRUCT/UENUM | ✅ C++→BP | ✅ Blueprint/Map | GAS、BP 對應、BT/ST、ABP/Montage |
| Axmol / Cocos2d-x (C++) | ✅ Tree-sitter | ✅ | — | EventDispatcher/Scheduler 綁定 |
| .NET (C#) | ✅ | ✅ | — | |
| 通用 C++ | ✅ | ✅ | — | |

---

*MCP 伺服器 → [gdep-cli/gdep_mcp/README_ZH_TW.md](./gdep-cli/gdep_mcp/README_ZH_TW.md)*
*CI/CD 整合 → [docs/ci-integration_ZH_TW.md](./docs/ci-integration_ZH_TW.md)*
*效能基準 → [docs/BENCHMARK_ZH_TW.md](./docs/BENCHMARK_ZH_TW.md)*
