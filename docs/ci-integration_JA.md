# gdep CI/CD 統合ガイド

> Unity / UE5 プロジェクトの GitHub リポジトリに gdep を組み込む方法です。
> そのままコピー＆ペーストして使えるように書いています。

---

## 概念の一言まとめ

| 用語 | 意味 |
|------|------|
| **CI** | PR を上げるたびに自動で「このコード大丈夫？」と検査する |
| **CD** | バージョンタグを付けると自動でデプロイされる |
| **ゲート** | 検査失敗時に PR のマージをブロックする仕組み |

---

## シナリオ 1 — Unity プロジェクト PR ゲート

PR ごとに gdep が **新しい循環参照** の発生を検査します。
循環参照が生じると PR のマージボタンが赤くなります。

```yaml
# .github/workflows/gdep-gate.yml  (Unity リポに追加)
name: gdep Quality Gate

on:
  pull_request:
    branches: [ main, master, develop ]
    paths:
      - 'Assets/Scripts/**'   # Scripts フォルダ変更時のみ実行

jobs:
  gdep-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - uses: actions/setup-dotnet@v4
        with:
          dotnet-version: '8.0.x'

      - name: Install gdep
        run: pip install gdep

      - name: Check for new circular dependencies
        run: |
          gdep diff Assets/Scripts --commit HEAD~1 --fail-on-cycles
```

---

## シナリオ 2 — UE5 プロジェクト + Lint レポート

PR ごとにアンチパターン (Tick 内 SpawnActor、Super:: 呼び出し漏れ等) を検査し、
結果を **JSON アーティファクト** として保存します。後から Actions タブでダウンロード可能。

```yaml
# .github/workflows/gdep-gate.yml  (UE5 版)
name: gdep Quality Gate

on:
  pull_request:
    branches: [ main ]
    paths:
      - 'Source/**'

jobs:
  gdep-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install gdep
        run: pip install gdep

      - name: Lint — anti-pattern scan
        run: |
          gdep lint Source/MyGame --format json > lint-report.json
          python3 -c "
          import json, sys
          d = json.load(open('lint-report.json'))
          errors = [x for x in d if x.get('severity') == 'Error']
          warnings = [x for x in d if x.get('severity') == 'Warning']
          print(f'Issues: {len(d)} total, {len(errors)} errors, {len(warnings)} warnings')
          # ルール: UE5-GAS-001 (CommitAbility 漏れ), UE5-BASE-001 (Super 漏れ),
          #         UE5-GAS-002 (高コストクエリ), UE5-NET-001 (ReplicatedUsing 漏れ) など
          if errors:
              for e in errors: print(f'  ERROR [{e[\"rule_id\"]}]: {e[\"class_name\"]} — {e[\"message\"]}')
              sys.exit(1)
          "

      - name: Upload lint report
        if: always()   # 失敗してもアーティファクト保存
        uses: actions/upload-artifact@v4
        with:
          name: gdep-lint-report
          path: lint-report.json
```

---

## シナリオ 3 — gdep 自体のリリース (バージョンタグ → PyPI 自動デプロイ)

gdep 自体のバージョンを上げるときに使います。

```bash
# 1. pyproject.toml のバージョンは CI がタグから自動的に上書きします。
#    手動変更は不要です。

# 2. タグを push するだけで release.yml がすべて処理します。
git tag v0.2.0
git push origin v0.2.0

# 自動で行われること:
#   1. gdep.dll をビルド
#   2. フロントエンドをビルド
#   3. PyPI にパッケージをアップロード
#   4. GitHub Release を作成 + dll zip を添付
```

### PyPI トークンの登録方法

1. https://pypi.org で API トークンを発行
2. GitHub リポ → Settings → Secrets and variables → Actions
3. `PYPI_API_TOKEN` という名前で登録
4. `release.yml` のコメントアウトされた `password:` 行を有効化

> **OIDC Trusted Publishing** を使えばトークンなしでもデプロイ可能です。
> PyPI プロジェクト設定で GitHub リポを信頼済みパブリッシャーとして登録してください。

---

## CI バッジ (README に追加)

```markdown
[![CI](https://github.com/pirua-game/gdep/actions/workflows/ci.yml/badge.svg)](https://github.com/pirua-game/gdep/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/gdep)](https://pypi.org/project/gdep/)
```

---

## 検出可能な Lint ルール (13個)

| Rule ID | エンジン | 説明 | 重大度 |
|---------|--------|------|--------|
| `UNI-PERF-001` | Unity | Update 内 GetComponent/Find 呼び出し | Error |
| `UNI-PERF-002` | Unity | Update 内 new/Instantiate 割り当て | Error |
| `UNI-ASYNC-001` | Unity | Coroutine while(true) 内 yield なし | Error |
| `UNI-ASYNC-002` | Unity | Coroutine 内 FindObjectOfType/Resources.Load | Warning |
| `UE5-PERF-001` | UE5 | Tick 内 SpawnActor/LoadObject | Error |
| `UE5-PERF-002` | UE5 | BeginPlay 内 同期 LoadObject | Warning |
| `UE5-BASE-001` | UE5 | Super:: 呼び出し漏れ | Warning |
| `UE5-GAS-001` | UE5 | ActivateAbility() 内 CommitAbility() 漏れ | Error |
| `UE5-GAS-002` | UE5 | GAS Ability 内 高コスト world クエリ | Warning |
| `UE5-GAS-003` | UE5 | BlueprintCallable が 10 個超 | Info |
| `UE5-GAS-004` | UE5 | BlueprintPure メソッドに const なし | Info |
| `UE5-NET-001` | UE5 | Replicated プロパティに ReplicatedUsing コールバックなし | Info |
| `GEN-ARCH-001` | 共通 | 循環参照 | Warning |

---

## フロー概要

```
PR をオープン
  └─ ci.yml 実行
       ├─ build-dll        C# dll ビルド
       ├─ lint-python      Python コード品質
       ├─ build-frontend   TypeScript ビルド確認
       ├─ test-linux       スモークテスト
       ├─ test-windows     スモークテスト
       └─ gate-cycles      新規循環参照 → ビルド失敗 (PR のみ)

git tag v* push
  └─ release.yml 実行
       ├─ build-dll        dll ビルド
       ├─ build-frontend   本番ビルド
       ├─ publish-pypi     PyPI デプロイ
       └─ create-release   GitHub Release + dll zip 添付
```
