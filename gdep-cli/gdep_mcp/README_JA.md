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

## 🛠 ツール一覧（13個）

| ツール | 説明 |
|--------|------|
| `get_project_context` | **セッション開始時に最初に呼び出す** — プロジェクト全体概要 |
| `analyze_impact_and_risk` | クラス変更前の波及範囲 + リント |
| `trace_gameplay_flow` | メソッド呼び出しチェーン追跡 + ソースコード |
| `inspect_architectural_health` | 結合度/循環参照/デッドコード/アンチパターン |
| `explore_class_semantics` | クラス構造 + AI 3行要約 |
| `execute_gdep_cli` | gdep CLI全機能への直接アクセス |
| `find_unity_event_bindings` | Unity Inspectorバインディング検出 |
| `analyze_unity_animator` | .controller → Layer/State/BlendTree構造 |
| `analyze_ue5_gas` | GA/GE/AS クラス + GameplayTag + ASC使用箇所 |
| `analyze_ue5_behavior_tree` | BT_* .uasset → Task/Decorator/Service |
| `analyze_ue5_state_tree` | ST_* .uasset → Task/AIController連携 |
| `analyze_ue5_animation` | ABPステートマシン + Montageセクション/GAS Notify |
| `analyze_ue5_blueprint_mapping` | C++クラス → BP実装マッピング |

---

*[メインリポジトリ](https://github.com/pirua-game/gdep)*
