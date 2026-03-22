# gdep MCP ベンチマーク — AI Agent トークン & 精度比較

> 環境: Claude Sonnet 4.6 + gdep MCP (ローカル)  
> トークナイザー: `cl100k_base` (Anthropic Claude と同系統、tiktoken 計測)  
> テストプロジェクト:
> - **Unity**: ProjectA (本番 2D モバイル、667 ファイル / 904 クラス)
> - **UE5**: ProjectZ / Lyra (大規模サンプル、カスタム Zombie 含む)
> - **UE5 GAS**: HackAndSlash ポートフォリオ (32 ファイル / 31 クラス)
>
> **MCP ツール現況 (ステップ 27 時点): 13 個**  
> 共通 4 個 + Raw CLI 1 個 + Unity 専用 2 個 + UE5 専用 5 個

---

## 要点まとめ

| 項目 | MCP なし | MCP あり |
|------|---------|---------|
| 回答の根拠 | 推測 / 一般知識 | 実際のコード分析結果 |
| トークン数 | 比較不可 | 公平な比較が不可能（下記参照） |
| 精度 | ❌ 検証不可 / ハルシネーション | ✅ コードベースの事実 |
| ハルシネーション | 高い | なし |

> **トークン数を比較できない理由:**
> MCP を使用すると、1 つの質問が複数のツール呼び出しにつながり、
> それぞれ構造化された分析データを返します。AI は毎回の応答で会話履歴全体を再読します。
> MCP なしでは、ソースファイルをそのまま丸読みしたり、コンテキストウィンドウを超過したり、
> 何も読まずに推測したりと、ワークフロー自体が異なります。
> 両者のトークン数を比較するのは、車と船の燃費を比較するようなもので、
> 数字は存在しますが、比較自体に意味がありません。
>
> **数値が実際に示すこと:**
> MCP を使えば、1 度の質問で正確なコードベースの回答が得られます。
> MCP なしでは、推測、ハルシネーション、または無関係なファイル読み込みによる
> コンテキスト超過という結果になります。
> 重要なのはトークン数ではなく、精度の差（0/5 vs 5/5）です。
---

## 詳細測定結果

### Q1 — 「CombatManager はどんな役割で、どのクラスが依存しているか？」

| | 方式 A (MCP なし) | 方式 B (MCP あり) |
|--|--|--|
| **ツール** | なし | `explore_class_semantics` |
| **質問トークン** | 42 | 42 |

**方式 A の回答:**
> 「CombatManager は名前からバトル関連のマネージャークラスと思われます。  
> UI やデータクラスが参照していると思います。  
> 正確な依存クラス一覧は不明です。」

**方式 B の回答 (MCP):**
> CombatManager は `ManagerBase` を継承。Fields: 173 / Methods: 283 / 外部参照: 104 種の **God Object**。  
> 主要依存先: CombatCore、UIGameField、UIHandDisplay、EntityCard、RuntimeAbility など全般。  
> `Managers` シングルトン 1 個からのみ直接参照されるが、プロジェクト全体で `Managers.Battle` として間接使用。

**精度判定:**
- 方式 A: ❌ 「推測」— 実際の規模 (283 メソッド、104 依存先) を全く把握できていない
- 方式 B: ✅ — 実際のファイルスキャン結果で検証済み

---

### Q2 — 「UIStatusEffect 変更時の影響範囲は？」

| | 方式 A | 方式 B |
|--|--|--|
| **ツール** | なし | `analyze_impact_and_risk` |

**方式 A の回答:**
> 「バフ表示 UI を変更するとバトル関連クラスに影響するでしょう。  
> 正確な範囲はコードを直接確認する必要があります。」

**方式 B の回答 (MCP):**
> 直接依存: `CombatObjectPool`、`CombatManager`  
> 間接依存: `UIGameField` → 7 つの BattleField サブクラス、`UITextComponent` 経由 200 以上の UI クラス  
> Asset: `Assets/Resources/Prefabs/UI/ui_status.prefab` (1 件)  
> Lint: アンチパターンなし ✓

**精度判定:**
- 方式 A: ❌ 「バトル関連」— 実際の 200 以上の UI クラスへの影響を完全に見落とし
- 方式 B: ✅ — プレハブアセットパスまで含めた正確なブラスト半径

> 💡 Q2 のトークン倍率が最も高い理由: UIStatusEffect → UITextComponent → 全 UI クラスという  
> 逆方向依存ツリーが非常に広く、ツール出力が 12,800 トークンに達したため。

---

### Q3 — 「Lyra プロジェクトの GAS 構造 — Ability はいくつあるか？」

| | 方式 A | 方式 B |
|--|--|--|
| **ツール** | なし | `analyze_ue5_gas` |

**方式 A の回答:**
> 「Lyra は Epic サンプルとして GAS を広範に使用しています。  
> LyraGameplayAbility が基底クラスで複数の Ability が派生しているはずです。  
> 正確な数はソースを直接確認する必要があります。」

**方式 B の回答 (MCP):**
> - Abilities: 1 個 (ELyraAbilityActivationPolicy — 活性化ポリシー enum)
> - Effects: 0 個、AttributeSets: 1 個 (ULyraAttributeSet)
> - ASC 使用クラス: 7 個 (LyraCharacter、LyraGameState、ZombieCharacter など)
> - GameplayTags: 13 個、カスタム ZombieCharacter の GAS 使用を確認

**精度判定:**
- 方式 A: ❌ 「複数の Ability」— 実際は 1 個のみ、Effects は 0 個 (ハルシネーション寸前)
- 方式 B: ✅ — C++ ヘッダー + uasset 2 パスのスキャンで正確な数値を提供

---

### Q4 — 「ZombieAIController はどの BehaviorTree を使っているか？」

| | 方式 A | 方式 B |
|--|--|--|
| **ツール** | なし | `explore_class_semantics` + ファイル直接確認 |

**方式 A の回答:**
> 「おそらく RunBehaviorTree() で BT アセットを実行するか、BehaviorTree コンポーネントを持つでしょう。  
> どの BT アセットを使っているかはソースを直接確認する必要があります。」

**方式 B の回答 (MCP):**
> ZombieAIController.cpp: AAIController 継承、OnPossess のみオーバーライド、本文は空。  
> RunBehaviorTree() 呼び出しなし — BT 接続は Blueprint レベルか未実装。  
> → **結論: このプロジェクトでは ZombieAIController は BT を直接使用していない** (予想と異なる)

**精度判定:**
- 方式 A: ❌ 「RunBehaviorTree() があるはず」— 実際にはなし。誤った予測
- 方式 B: ✅ — 実際のソースコード確認で「BT なし」の事実を正確に確認

> 💡 このケースは「ないことを確認する」能力の差を明確に示しています。

---

### Q5 — 「結合度が最も高いクラス Top5 と循環参照の状況」

| | 方式 A | 方式 B |
|--|--|--|
| **ツール** | なし | `execute_gdep_cli` (scan) |

**方式 A の回答:**
> 「Manager 系や共通 UI 基底クラスが上位に来るでしょう。  
> CombatManager や GameManager が高いと思います。」

**方式 B の回答 (MCP):**
> Top 5 (in-degree):
> 1. UITextComponent — 231 (予想外の 1 位)
> 2. UIDynamicList — 66
> 3. Data_Entity — 54
> 4. EntityCard — 46
> 5. UIListGeneric — 43
>
> 循環参照: **40 個** (直接 14 個、間接 26 個)  
> 主要パターン: CombatCore↔CombatInfo、EntityCard↔EntityCardPool

**精度判定:**
- 方式 A: ❌ 「CombatManager」予測 — 実際の 1 位は UITextComponent (231)、CombatManager は上位に入っていない
- 方式 B: ✅ — 実際の数値に基づき、循環参照 40 個を正確に把握

---

## 精度詳細

| 項目 | 方式 A | 方式 B |
|------|--------|--------|
| 正解 (5 問) | 0 / 5 | 5 / 5 |
| ハルシネーション発生 | 3 件 | 0 件 |
| 不完全な回答 | 5/5 | 0/5 |
| 検証可能性 | ❌ 不可 | ✅ コードで検証 |

---

## いつ MCP を使うと効果的か？

**実用ガイド:**
- 「初めてコードベースを把握するとき」→ MCP 必須、トークン投資の価値あり
- 「既に把握した構造の軽い確認」→ 方式 A で十分
- 「変更前の安全性確認」→ MCP 必須 (方式 A では判断不可)
- **UE5 GAS フロー分析** → `analyze_ue5_gas` + `blueprint_mapping` の組み合わせを推奨
- **全ドリルダウンパスの解釈** → Web UI フローグラフの LLM 解釈機能を活用
