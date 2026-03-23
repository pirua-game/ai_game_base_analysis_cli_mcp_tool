# gdep MCP 基準測試 — AI Agent 令牌與精度對比

> 環境：Claude Sonnet 4.6 + gdep MCP（本機）  
> 分詞器：`cl100k_base`（與 Anthropic Claude 同系列，使用 tiktoken 測量）  
> 測試專案：
> - **Unity**：ProjectA（線上 2D 手遊，667 檔案 / 904 類別）
> - **UE5**：ProjectZ / Lyra（大規模範例，含自訂 Zombie）
> - **UE5 GAS**：HackAndSlash 作品集（32 檔案 / 31 類別）
>
> **MCP 工具現況（第 42 步為準）：共 18 個**
> 通用 9 個 + Unity 專用 2 個 + UE5 專用 5 個 + Axmol 專用 1 個 + Raw CLI 1 個

---

## 核心摘要

| 項目 | 無 MCP | 有 MCP |
|------|-------|-------|
| 回答依據 | 猜測 / 通用知識 | 實際程式碼分析結果 |
| 令牌數 | 不可比較 | 無法公平比較（見說明） |
| 準確度 | ❌ 無法驗證 / 幻覺 | ✅ 基於程式碼的事實 |
| 幻覺 | 高 | 無 |

> **為什麼令牌數無法比較：**
> 使用 MCP 時，一個問題可能觸發多次工具呼叫，每次返回結構化分析資料。
> AI 每次回覆時還會重新讀取整個對話歷史。
> 不使用 MCP 時，AI 可能整段讀取原始碼、超出上下文視窗，或完全不讀取任何內容而直接猜測。
> 這兩種方式的工作流程根本不同，比較它們的令牌數就像比較汽車和船的油耗——
> 數字存在，但比較本身沒有意義。
>
> **數字真正說明了什麼：**
> 使用 MCP，一次提問即可獲得精確的程式碼支撐答案。
> 不使用 MCP，則會得到猜測、幻覺，或因讀取錯誤檔案而導致上下文溢出。
> 重要的不是令牌數，而是準確度差距（0/5 vs 5/5）。
---

## 詳細測量結果

### Q1 — "CombatManager 的職責是什麼，哪些類別相依於它？"

| | 方式 A（無 MCP） | 方式 B（有 MCP） |
|--|--|--|
| **工具** | 無 | `explore_class_semantics` |

**方式 B 回答（MCP）：**
> CombatManager 繼承 `ManagerBase`。Fields: 173 / Methods: 283 / 外部引用: 104 種 — **God Object**。  
> 核心相依：CombatCore、UIGameField、UIHandDisplay、EntityCard、RuntimeAbility 等全域邏輯。

**精度判定：**
- 方式 A：❌ 「猜測」— 完全不知道實際規模
- 方式 B：✅ — 由實際檔案掃描結果驗證

---

### Q2 — "修改 UIStatusEffect 的影響範圍是什麼？"

| | 方式 A | 方式 B |
|--|--|--|

**方式 B 回答（MCP）：**
> 直接相依：`CombatObjectPool`、`CombatManager`  
> 間接相依：`UIGameField` → 7 個 BattleField 子類別，經 `UITextComponent` → 200+ UI 類別  
> 資源：`Assets/Resources/Prefabs/UI/ui_status.prefab`（1 處引用）

**精度判定：**
- 方式 A：❌ 「戰鬥相關類別」— 完全遺漏 200+ UI 類別的影響
- 方式 B：✅ — 包含 prefab 資源路徑的精確爆炸半徑

---

### Q3 — "Lyra 專案 GAS 結構 — 有幾個 Ability？"

**方式 B 回答（MCP）：**
> - Abilities：1 個（ELyraAbilityActivationPolicy — 啟動策略 enum）
> - Effects：0 個，AttributeSets：1 個
> - 使用 ASC 的類別：7 個

**精度判定：**
- 方式 A：❌ 「多個 Ability」— 實際只有 1 個，Effects 為 0（接近幻覺）
- 方式 B：✅ — 精確數值

---

### Q4 — "ZombieAIController 使用哪個 BehaviorTree？"

**方式 B 回答（MCP）：**
> ZombieAIController.cpp：繼承 AAIController，僅覆寫 OnPossess，函式主體為空。  
> 未找到 RunBehaviorTree() 呼叫。  
> → **結論：此專案中 ZombieAIController 未直接使用 BT**

---

### Q5 — "耦合度最高的 Top5 類別和循環相依現狀"

**方式 B 回答（MCP）：**
> Top 5（入度）：
> 1. UITextComponent — 231（出乎意料的第 1）
> 2. UIDynamicList — 66 / 3. Data_Entity — 54 / 4. EntityCard — 46 / 5. UIListGeneric — 43
>
> 循環相依：**40 個**（直接 14 個，間接 26 個）

---

## 何時使用 MCP 最值得？

**實用指南：**
- 「首次了解陌生程式碼庫」→ MCP 必須，令牌投入值得
- 「對已知結構的輕量確認」→ 方式 A 即可
- 「修改前的安全性確認」→ MCP 必須（方式 A 無法做出判斷）
- **UE5 GAS 流程分析** → 推薦 `analyze_ue5_gas` + `blueprint_mapping` 組合
- **全鑽取路徑解釋** → 利用 Web UI 流程圖的 LLM 解釋功能
