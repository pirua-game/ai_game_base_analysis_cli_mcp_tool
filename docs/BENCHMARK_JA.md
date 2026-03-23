# 📊 gdep パフォーマンスベンチマーク

> **測定環境**: Windows 11、AMD Ryzen (64-bit)、32 GB RAM  
> **ストレージ**: UE5 ProjectZ — HDD (NVMe)、Unity ProjectA — NVMe SSD (`F:\`)  
> **測定ツール**: [hyperfine](https://github.com/sharkdp/hyperfine) v1.20.0、[memory_profiler](https://github.com/pythonprofilers/memory_profiler) v0.61  
> **測定日**: 2026-03-22  

---

## テストプロジェクト規模

| プロジェクト | エンジン | 規模 |
|------------|--------|------|
| **ProjectZ** (Lyraベース) | UE5 | C++ソース 241ファイル / 2,898 uasset·umap / プラグイン 9個 |
| **CommercialMobileGame** (本番モバイル) | Unity C# | 667 `.cs` ファイル / 904クラス / 循環参照 40個 |

---

## ケース A — Cold vs Warm キャッシュ性能 ⭐

> `mtime` ベースのディスクキャッシュ (`.gdep_cache/`) の実際の効果を測定します。

### UE5 ProjectZ

| 指標 | 数値 | 備考 |
|------|------|------|
| Cold Scan (平均) | **1.432 s** | 3回測定 |
| Cold Scan (最小) | **0.723 s** | キャッシュ削除後の初回実行 |
| Warm Scan (平均) | **0.467 s** ± 9.1 ms | 5回測定 |
| Warm Scan (最小) | **0.456 s** | |
| **キャッシュ高速化** | **~3×** (cold min 基準) | |

### Unity CommercialMobileGame (SSD — `D:\Projects\GameClient`)

| 指標 | 数値 | 備考 |
|------|------|------|
| Cold Scan (平均) | **3.342 s** | 3回測定、1回目はOSファイルキャッシュ未適用 |
| Cold Scan (最小) | **0.465 s** | OSファイルキャッシュウォームアップ後 |
| Warm Scan (平均) | **0.487 s** ± 33.2 ms | 5回測定 |
| Warm Scan (最小) | **0.460 s** | |
| **キャッシュ高速化** | **~7×** (cold mean 基準) | |

> **HDD vs SSD**: HDD (`D:\`) では cold 平均 559 ms / warm 469 ms — ほぼ差なし。  
> SSD では cold 3.3 s → warm 0.49 s — **キャッシュ効果が 6〜7 倍**。  
> HDD では dotnet subprocess 起動コストが I/O コストを上回るため、キャッシュ効果が小さい。

---

## ケース B — インクリメンタルアップデート

> ファイル 1 件変更後の再スキャン時間 (部分キャッシュ無効化の確認)

| プロジェクト | Cold | Warm (変更なし) | Incremental (1ファイル変更) | 目標 |
|------------|------|----------------|--------------------------|------|
| UE5 ProjectZ | 0.69 s | **0.438 s** | **0.69 s** | < 3 s ✅ |
| Unity CommercialMobileGame (SSD) | 0.43 s | **0.411 s** | **3.79 s** | < 3 s ⚠️ |

> Unity incremental 3.79 s は `dotnet` subprocess 再起動のオーバーヘッド (~3 s) を含む。  
> キャッシュフィンガープリント検査自体は 20 ms 以下で、変更されたファイルのみ再パース。

---

## ケース C — 機能別分析時間

| 機能 | 対象 | 平均 | 備考 |
|------|------|------|------|
| `gdep scan` | UE5 ProjectZ (warm) | **0.467 s** | |
| `gdep scan` | Unity ProjectA (warm) | **0.487 s** | |
| `gdep lint` | UE5 ProjectZ | **1.858 s** | 3回平均、初回 3.05 s |
| `gdep describe` | UE5 `UARGamePlayAbility_BasicAttack` | **1.267 s** | |
| `gdep describe` | Unity `CombatCore` | **3.018 s** | C# パース含む |

---

## ケース D — メモリプロファイリング

> `memory_profiler` で測定したピーク RSS。目標: UE5 < 300 MB、Unity < 200 MB。

| プロジェクト | ピークメモリ | 目標 | 結果 |
|------------|------------|------|------|
| UE5 ProjectZ | **28.5 MB** | < 300 MB | ✅ PASS |
| Unity CommercialMobileGame | **29.3 MB** | < 200 MB | ✅ PASS |

> 両プロジェクトとも **30 MB 以下**。目標に対して **10 倍以上の余裕**。  
> Python プロセスのベースライン (~20 MB) を含む値で、純粋な分析メモリは ~10 MB 程度。

---

## ケース F — MCP サーバー機能別レスポンス

> UE5 ProjectZ 基準。Cold = キャッシュ削除後、Warm = キャッシュ保持。

| 機能 | Cold | Warm | 高速化 |
|------|------|------|--------|
| `analyze_gas` | **28.8 s** | **0.094 s** | **307×** 🚀 |
| `build_bp_map` | **4.2 s** | **0.076 s** | **55×** 🚀 |
| `analyze_behavior_tree` | **3.3 s** | **0.079 s** | **41×** 🚀 |
| `analyze_state_tree` | **3.0 s** | **0.077 s** | **39×** 🚀 |
| `analyze_abp` | **4.1 s** | **0.086 s** | **48×** 🚀 |

> **ステップ 30 改善**: `uasset_cache.py` 共通キャッシュレイヤーを追加し、全関数 warm 0.1 s 以下を達成。  
> キャッシュ有効性は Content ルートの mtime フィンガープリント (`os.scandir` ベース、~20 ms) で検証。  
> Cold 数値は uasset バイナリ全スキャンを含む初回実行基準。

---

## 総合サマリー

| 指標 | 数値 | 目標 |
|------|------|------|
| UE5 Cold Scan | 0.72 s | < 30 s ✅ |
| UE5 Warm Scan | **0.46 s** | < 1 s ✅ |
| Unity Cold Scan (SSD) | 0.47 s | < 15 s ✅ |
| Unity Warm Scan (SSD) | **0.49 s** | < 0.5 s ✅ |
| UE5 Incremental (1ファイル) | **0.69 s** | < 3 s ✅ |
| Unity Incremental (1ファイル) | 3.79 s | < 3 s ⚠️ |
| UE5 ピークメモリ | **28.5 MB** | < 300 MB ✅ |
| Unity ピークメモリ | **29.3 MB** | < 200 MB ✅ |
| `analyze_gas` warm | **0.094 s** | — 🚀 |
| `build_bp_map` warm | **0.076 s** | — 🚀 |
| `analyze_abp` warm | **0.086 s** | — 🚀 |
| `analyze_behavior_tree` warm | **0.079 s** | — 🚀 |

---

## ケース G — Web UI 新機能レスポンス時間 (ステップ 42)

> FastAPI エンドポイント直接呼び出し基準。テスト環境: macOS (M シリーズ)、Unity TrumpCard。

| 機能 | エンドポイント | Cold | Warm | 備考 |
|------|-------------|------|------|------|
| 🧪 テスト範囲 | `POST /project/test-scope` | ~22 s | **~1-2 s** | impact BFS + ファイルスキャン含む |
| 🏗️ アーキテクチャアドバイザー | `POST /project/advise` | ~1 s | **0.12 s** | scan+lint キャッシュ活用 |
| 📋 Lint Fix スキャン | `POST /project/lint-fix` | ~22 s | **~1-2 s** | lint JSON + fix_suggestion フィルタ |
| 📊 Diff 要約 | `POST /project/diff-summary` | ~5 s | **~5 s** | subprocess gdep diff (キャッシュ無し) |
| 🪓 Axmol Events | `POST /engine/axmol/events` | **< 0.5 s** | **< 0.5 s** | C++ 正規表現スキャン |

---

## 残存ボトルネック

| 項目 | 現状 | 改善案 | 期待効果 |
|------|------|--------|--------|
| Unity Incremental | 3.79 s (dotnet 再起動含む) | dotnet プロセスを長期維持 or 変更ファイルのみパッチ | < 1 s |
| `build_bp_map` cold | 4.2 s → warm 0.076 s ✅ | ~~uasset mtime キャッシュ~~ 完了 | — |
| `analyze_gas` cold | 28.8 s → warm 0.094 s ✅ | ~~キャッシュ~~ 完了 | — |
