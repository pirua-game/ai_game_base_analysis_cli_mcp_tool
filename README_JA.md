# 🎮 gdep — ゲームコードベース解析ツール

**Unity・UE5・Axmol 大規模プロジェクトを 0.5 秒で把握し、Claude/Cursor に実際のコードを読ませる**

[![CI](https://github.com/pirua-game/gdep/actions/workflows/ci.yml/badge.svg)](https://github.com/pirua-game/gdep/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/gdep)](https://pypi.org/project/gdep/)
[![npm](https://img.shields.io/npm/v/gdep-mcp)](https://www.npmjs.com/package/gdep-mcp)

> *「このクラスを変更したらどこまで影響する？」* — 3秒で正確に回答、ハルシネーション 0 件

**他の言語で読む:**
[English](./README.md) · [한국어](./README_KR.md) · [简体中文](./README_ZH.md) · [繁體中文](./README_ZH_TW.md)

---

## ✨ なぜ gdep を使うのか？

大規模なゲームクライアントは苦痛です:

- UE5 Blueprint 300 個以上 → *「この Ability はどこから呼ばれている？」* — 半日が消える
- Unity Manager 50 個 + Prefab 参照 → リファクタリングで循環参照が爆発
- *「このクラスを変更したら何が壊れる？」* → 手動で 30 分追跡

**gdep はこれをすべて 0.5 秒で解決します。**

### 実測パフォーマンス

| 指標 | 数値 | 備考 |
|------|------|------|
| UE5 warm scan | **0.46 秒** | uasset 2,800 件以上のプロジェクト |
| Unity warm scan | **0.49 秒** | SSD 環境、クラス 900 件以上 |
| ピークメモリ | **28.5 MB** | 目標の 10 倍の余裕 |
| MCP 精度 | **5/5 (100%)** | コードベースの事実 |

> 詳細 → [docs/BENCHMARK_JA.md](./docs/BENCHMARK_JA.md) · [docs/mcp-benchmark_JA.md](./docs/mcp-benchmark_JA.md)

---

## 🤖 MCP 連携 — AI に実際のコードを読ませる

gdep は Claude Desktop、Cursor など MCP 対応 AI エージェント向けの MCP サーバーを提供します。

### 1 行でインストール

```bash
npm install -g gdep-mcp
```

### エージェント設定（コピー&ペースト）

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

設定完了。Claude · Cursor · Gemini が毎会話でゲームエンジン特化の **18 個** のツールを使えます。

### MCP が変えること

```
通常 Claude: 「CombatCore には Manager 系の依存があるようです...」← 推測
gdep MCP:   直接依存 2 件 · 間接 200 件以上の UI クラス · アセット: prefabs/UI/combat.prefab
```

### MCP ツール一覧（18 個）

| ツール | 使用タイミング |
|--------|-------------|
| `get_project_context` | **必ず最初に呼び出す** — プロジェクト全体概要 |
| `analyze_impact_and_risk` | クラス変更前の安全確認 |
| `trace_gameplay_flow` | C++ → Blueprint 呼び出しチェーン追跡 |
| `inspect_architectural_health` | 技術的負債の全体診断 |
| `explore_class_semantics` | 未知クラスの詳細把握 |
| `suggest_test_scope` | クラス変更後に実行すべきテストファイル自動特定 |
| `suggest_lint_fixes` | lint 問題 + コード修正提案（dry-run） |
| `summarize_project_diff` | git diff をアーキテクチャ観点で要約 |
| `get_architecture_advice` | プロジェクト総合診断 + LLM アーキテクチャアドバイス |
| `execute_gdep_cli` | CLI 全機能への直接アクセス |
| `find_unity_event_bindings` | Inspector 連結メソッド（コード検索不可領域） |
| `analyze_unity_animator` | Animator ステートマシン構造 |
| `analyze_axmol_events` | Axmol EventDispatcher/Scheduler バインディングマップ |
| `analyze_ue5_gas` | GAS Ability / Effect / Tag / ASC 全体 |
| `analyze_ue5_behavior_tree` | BehaviorTree アセット構造 |
| `analyze_ue5_state_tree` | StateTree アセット構造 |
| `analyze_ue5_animation` | ABP 状態 + Montage + GAS Notify |
| `analyze_ue5_blueprint_mapping` | C++ クラス → Blueprint 実装マッピング |

> 詳細設定 → [gdep-cli/gdep-mcp/README_JA.md](./gdep-cli/gdep-mcp/README_JA.md)

---

## 📦 インストール

| 項目 | バージョン | 用途 |
|------|-----------|------|
| Python | 3.11+ | CLI · MCP サーバー |
| .NET Runtime | 8.0+ | C# / Unity プロジェクト解析 |

```bash
# Windows
install.bat

# macOS / Linux
chmod +x install.sh && ./install.sh
```

---

## 🚀 クイックスタート

```bash
gdep detect {path}                     # エンジン自動検出
gdep scan {path} --circular --top 15   # 構造分析
gdep init {path}                       # .gdep/AGENTS.md 生成
gdep advise {path}                     # アーキテクチャ診断 + アドバイス
```

---

## 🖥️ Web UI — ブラウザで視覚的に分析する

インストール後はターミナル不要。ブラウザで依存グラフ・呼び出しフロー・AI チャットを利用できます。

**ステップ 1 — インストール**（プロジェクトルートで初回のみ）

```
install.bat          # Windows
./install.sh         # macOS / Linux
```

**ステップ 2 — 起動**

```
run.bat              # Windows — バックエンド + フロントエンドを別々の 2 ターミナルで自動起動
./run.sh             # macOS/Linux — ターミナル 1: バックエンド  (http://localhost:8000)
./run_front.sh       # macOS/Linux — ターミナル 2: フロントエンド (http://localhost:5173)
```

`http://localhost:5173` にアクセス → サイドバーでプロジェクトのソースフォルダを指定

主な機能:
- インタラクティブな依存グラフ・呼び出しフローの可視化
- クラスブラウザ（影響分析・lint 付き）
- 実際のコードを読む AI チャットエージェント（ツールコーリング）
- エンジン専用エクスプローラー: GAS · Blueprint マッピング · Animator · BehaviorTree · StateTree

> UI 対応言語: **英語と韓国語のみ** · ローカル LLM: **Ollama** 対応 · 非商用ツールのため一部機能が完全でない場合があります

詳細ドキュメント → [gdep-cli/web/README.md](./gdep-cli/web/README.md)

---

## 🎯 コマンドリファレンス

| コマンド | 概要 | 使用タイミング |
|---------|------|-------------|
| `detect` | エンジン自動検出 | 最初の解析前 |
| `scan` | 結合度・循環参照・デッドコード | 構造把握、リファクタリング前 |
| `describe` | クラス詳細 + Blueprint 実装 + AI 要約 | 未知クラス、コードレビュー |
| `flow` | 呼び出しチェーン（C++→BP 境界） | バグ追跡、フロー解析 |
| `impact` | 変更波及効果の逆追跡 | リファクタリング前の安全確認 |
| `test-scope` | クラス変更後に実行すべきテストファイル | マージ前、CI 計画 |
| `watch` | リアルタイムファイル変更監視 (impact+test+lint) | 開発中の常時モニタリング |
| `lint` | ゲーム特化アンチパターン 16 個（+ `--fix`） | PR 品質チェック |
| `advise` | 全体アーキテクチャ診断 + LLM アドバイス | アーキテクチャレビュー |
| `graph` | 依存関係グラフ export | ドキュメント化、可視化 |
| `diff` | コミット前後の依存比較 | PR レビュー、CI ゲート |
| `init` | AI Agent コンテキスト生成 | **AI コーディング初期設定** |
| `context` | コンテキスト出力 | AI チャットへのコピー |
| `hints` | シングルトンヒント管理 | flow 精度向上 |
| `config` | LLM 設定 | AI 要約機能使用前 |

---

## 🎮 対応エンジン

| エンジン | クラス解析 | フロー解析 | 逆参照 | 特化機能 |
|---------|-----------|----------|--------|---------|
| Unity (C#) | ✅ | ✅ | ✅ Prefab/Scene | UnityEvent、Animator |
| Unreal Engine 5 | ✅ UCLASS/USTRUCT/UENUM | ✅ C++→BP | ✅ Blueprint/Map | GAS、BP マッピング、BT/ST、ABP/Montage |
| Axmol / Cocos2d-x (C++) | ✅ Tree-sitter | ✅ | — | EventDispatcher/Scheduler バインディング |
| .NET (C#) | ✅ | ✅ | — | |
| 汎用 C++ | ✅ | ✅ | — | |

---

*MCP サーバー → [gdep-cli/gdep-mcp/README_JA.md](./gdep-cli/gdep-mcp/README_JA.md)*
*CI/CD 連携 → [docs/ci-integration_JA.md](./docs/ci-integration_JA.md)*
*パフォーマンス → [docs/BENCHMARK_JA.md](./docs/BENCHMARK_JA.md)*
