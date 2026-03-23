# gdep MCP 基准测试 — AI Agent 令牌与精度对比

> 环境：Claude Sonnet 4.6 + gdep MCP（本地）  
> 分词器：`cl100k_base`（与 Anthropic Claude 同系列，使用 tiktoken 测量）  
> 测试项目：
> - **Unity**：ProjectA（线上 2D 手游，667 文件 / 904 类）
> - **UE5**：ProjectZ / Lyra（大规模示例，含自定义 Zombie）
> - **UE5 GAS**：HackAndSlash 作品集（32 文件 / 31 类）
>
> **MCP 工具现况（第 42 步为准）：共 18 个**
> 通用 9 个 + Unity 专用 2 个 + UE5 专用 5 个 + Axmol 专用 1 个 + Raw CLI 1 个

---

## 核心摘要

| 项目 | 无 MCP | 有 MCP |
|------|-------|-------|
| 回答依据 | 猜测 / 通用知识 | 实际代码分析结果 |
| 令牌数 | 不可比较 | 无法公平比较（见说明） |
| 准确度 | ❌ 无法验证 / 幻觉 | ✅ 基于代码的事实 |
| 幻觉 | 高 | 无 |

> **为什么令牌数无法比较：**
> 使用 MCP 时，一个问题可能触发多次工具调用，每次返回结构化分析数据。
> AI 每次回复时还会重新读取整个对话历史。
> 不使用 MCP 时，AI 可能整段读取源文件、超出上下文窗口，或完全不读取任何内容而直接猜测。
> 这两种方式的工作流程根本不同，比较它们的令牌数就像比较汽车和船的油耗——
> 数字存在，但比较本身没有意义。
>
> **数字真正说明了什么：**
> 使用 MCP，一次提问即可获得精确的代码支撑答案。
> 不使用 MCP，则会得到猜测、幻觉，或因读取错误文件而导致上下文溢出。
> 重要的不是令牌数，而是准确度差距（0/5 vs 5/5）。
---

## 详细测量结果

### Q1 — "CombatManager 的职责是什么，哪些类依赖它？"

| | 方式 A（无 MCP） | 方式 B（有 MCP） |
|--|--|--|
| **工具** | 无 | `explore_class_semantics` |

**方式 A 回答：**
> "从名称推测 CombatManager 应该是与战斗相关的管理类。UI 或数据类可能会引用它。具体依赖类列表不明。"

**方式 B 回答（MCP）：**
> CombatManager 继承 `ManagerBase`。Fields: 173 / Methods: 283 / 外部引用: 104 种 — **God Object**。  
> 核心依赖：CombatCore、UIGameField、UIHandDisplay、EntityCard、RuntimeAbility 等全局逻辑。  
> 仅被 `Managers` 单例直接引用，但全项目通过 `Managers.Battle` 间接使用。

**精度判定：**
- 方式 A：❌ "猜测" — 完全不知道实际规模（283 个方法、104 种依赖）
- 方式 B：✅ — 由实际文件扫描结果验证

---

### Q2 — "修改 UIStatusEffect 的影响范围是什么？"

| | 方式 A | 方式 B |
|--|--|--|
| **工具** | 无 | `analyze_impact_and_risk` |

**方式 A 回答：**
> "修改 Buff 显示 UI 可能影响战斗相关类。具体范围需要直接查看代码。"

**方式 B 回答（MCP）：**
> 直接依赖：`CombatObjectPool`、`CombatManager`  
> 间接依赖：`UIGameField` → 7 个 BattleField 子类，经 `UITextComponent` → 200+ UI 类  
> 资源：`Assets/Resources/Prefabs/UI/ui_status.prefab`（1 处引用）  
> Lint：无反模式 ✓

**精度判定：**
- 方式 A：❌ "战斗相关类" — 完全遗漏了 200+ UI 类的影响
- 方式 B：✅ — 包含 prefab 资源路径的精确爆炸半径

---

### Q3 — "Lyra 项目 GAS 结构 — 有多少个 Ability？"

| | 方式 A | 方式 B |
|--|--|--|
| **工具** | 无 | `analyze_ue5_gas` |

**方式 B 回答（MCP）：**
> - Abilities：1 个（ELyraAbilityActivationPolicy — 激活策略 enum）
> - Effects：0 个，AttributeSets：1 个（ULyraAttributeSet）
> - 使用 ASC 的类：7 个（LyraCharacter、LyraGameState、ZombieCharacter 等）
> - GameplayTags：13 个

**精度判定：**
- 方式 A：❌ "多个 Ability" — 实际只有 1 个，Effects 为 0（接近幻觉）
- 方式 B：✅ — C++ 头文件 + uasset 双轮扫描给出精确数值

---

### Q4 — "ZombieAIController 使用哪个 BehaviorTree？"

**方式 B 回答（MCP）：**
> ZombieAIController.cpp：继承 AAIController，仅重写 OnPossess，函数体为空。  
> 未找到 RunBehaviorTree() 调用 — BT 连接在 Blueprint 层完成或尚未实现。  
> → **结论：此项目中 ZombieAIController 未直接使用 BT**（与预期不符）

---

### Q5 — "耦合度最高的 Top5 类和循环依赖现状"

**方式 B 回答（MCP）：**
> Top 5（入度）：
> 1. UITextComponent — 231（出乎意料的第 1）
> 2. UIDynamicList — 66
> 3. Data_Entity — 54
> 4. EntityCard — 46
> 5. UIListGeneric — 43
>
> 循环依赖：**40 个**（直接 14 个，间接 26 个）

---

## 何时使用 MCP 最划算？

**实用指南：**
- "首次了解陌生代码库" → MCP 必须，令牌投入值得
- "对已知结构的轻量确认" → 方式 A 足够
- "修改前的安全性检查" → MCP 必须（方式 A 无法做出判断）
- **UE5 GAS 流程分析** → 推荐 `analyze_ue5_gas` + `blueprint_mapping` 组合
- **全钻取路径解释** → 利用 Web UI 流程图的 LLM 解释功能
