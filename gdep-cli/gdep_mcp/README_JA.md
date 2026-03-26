# gdep-mcp — ゲームコードベース解析 MCPサーバー

Claude Desktop、CursorなどのAIエージェントで[gdep](https://github.com/pirua-game/gdep)を使用して
ゲームプロジェクト（Unity、UE5、C++、C#）を解析できるMCPサーバーです。

**他の言語で読む:**
[English](./README.md) · [한국어](./README_KR.md) · [简体中文](./README_ZH.md) · [繁體中文](./README_ZH_TW.md)

---

## ⚡ クイックインストール

### npm でインストール（推奨 — git clone 不要）

```bash
npm install -g gdep-mcp
```

`gdep` と `mcp[cli]` Python パッケージも自動的にインストールされます。

AIエージェントの設定に追加:

```json
{
  "mcpServers": {
    "gdep": {
      "command": "gdep-mcp"
    }
  }
}
```

> 各ツール呼び出し時に `project_path` をパラメータとして渡します。設定にプロジェクトパス不要。

### pip で手動インストール

```bash
pip install gdep "mcp[cli]"
```

---

## 🛠 ツール一覧（19個）

### コンテキストツール

| ツール | 説明 |
|--------|------|
| `get_project_context` | **セッション開始時に最初に呼び出す** — プロジェクト全体概要 |

### ハイレベル意図ベースツール（9個）

| ツール | 説明 |
|--------|------|
| `analyze_impact_and_risk` | クラス変更前の波及範囲 + リント。`detail_level="summary"` で高速要約；`query=` で結果フィルタ |
| `explain_method_logic` | 単一メソッドの内部制御フロー要約 — Guard/Branch/Loop/Always を5〜10行で |
| `trace_gameplay_flow` | メソッド呼び出しチェーン追跡 + ソースコード |
| `inspect_architectural_health` | 結合度/循環参照/デッドコード/アンチパターン |
| `explore_class_semantics` | クラス構造 + AI 3行要約 |
| `suggest_test_scope` | クラス変更後に実行すべきテストファイル自動特定（CI JSON出力対応） |
| `suggest_lint_fixes` | lint問題 + コード修正提案（dry-run、ファイル変更なし） |
| `summarize_project_diff` | git diffをアーキテクチャ観点で要約 — 循環参照増減・高結合警告 |
| `get_architecture_advice` | scan+lint+impact総合 → 構造化レポートまたはLLMアーキテクチャアドバイス |

### Raw CLIアクセス

| ツール | 説明 |
|--------|------|
| `execute_gdep_cli` | gdep CLI全機能への直接アクセス |

### Axmol / Cocos2d-x専用

| ツール | 説明 |
|--------|------|
| `analyze_axmol_events` | EventDispatcher/Schedulerバインディングマップ — イベント登録/処理主体の抽出 |

### Unity専用

| ツール | 説明 |
|--------|------|
| `find_unity_event_bindings` | Unity Inspectorバインディング検出 |
| `analyze_unity_animator` | .controller → Layer/State/BlendTree構造 |

### UE5専用

| ツール | 説明 |
|--------|------|
| `analyze_ue5_gas` | GA/GE/AS クラス + GameplayTag + ASC使用箇所。**信頼度ヘッダー**（分析方法/信頼ティア/カバレッジ/UEバージョン）+ IS-Aアセット役割分類（GA/GE/AS/ABP vs 参照のみ）を含む。GUIDノイズタグをフィルタリング。`enum class` 誤検知修正済み。 |
| `analyze_ue5_behavior_tree` | BT_* .uasset → Task/Decorator/Service |
| `analyze_ue5_state_tree` | ST_* .uasset → Task/AIController連携 |
| `analyze_ue5_animation` | ABPステートマシン + Montageセクション/GAS Notify |
| `analyze_ue5_blueprint_mapping` | C++クラス → BP実装マッピング。**信頼度ヘッダー**（カバレッジ + UEバージョン）を含む。 |

---

## 🔍 UE5 信頼度透明化出力

`analyze_ue5_gas` と `analyze_ue5_blueprint_mapping` はすべての応答の先頭に信頼度ヘッダーを出力します：

```
> Analysis method: cpp_source_regex + binary_pattern_match
> Confidence: **MEDIUM**
> Coverage: 4633/4633 assets parsed (100.0%)
> UE version: 5.6 (validated)
```

| ティア | 根拠 | ガイダンス |
|--------|------|----------|
| **HIGH** | C++ソース直接解析 | 追加検証なしで信頼可能 |
| **MEDIUM** | バイナリ NativeParentClass + 相互参照 | ほぼ信頼可能；アーキテクチャ決定前にソース確認推奨 |
| **LOW** | ファイル名ヒューリスティック / LFS スタブ 50%超 | インデックスとして使用のみ；変更前にソースを直接確認 |

`gdep init` が生成する `.gdep/AGENTS.md` に、Confidence レベル別のAIエージェント行動ガイドが含まれます。

---

*[メインリポジトリ](https://github.com/pirua-game/gdep)*
