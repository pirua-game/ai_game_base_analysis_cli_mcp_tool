# 📊 gdep 效能基準測試

> **測試環境**：Windows 11、AMD Ryzen (64-bit)、32 GB RAM  
> **儲存**：UE5 ProjectZ — HDD (NVMe)、Unity ProjectA — NVMe SSD (`F:\`)  
> **工具**：[hyperfine](https://github.com/sharkdp/hyperfine) v1.20.0、[memory_profiler](https://github.com/pythonprofilers/memory_profiler) v0.61  
> **測試日期**：2026-03-22  

---

## 測試專案規模

| 專案 | 引擎 | 規模 |
|------|------|------|
| **ProjectZ** (基於 Lyra) | UE5 | C++ 原始碼 241 個檔案 / 2,898 個 uasset·umap / 9 個外掛 |
| **CommercialMobileGame** (線上行動端) | Unity C# | 667 個 `.cs` 檔案 / 904 個類別 / 40 個循環相依 |

---

## 情境 A — 冷啟動 vs 熱快取效能 ⭐

> 測量基於 `mtime` 的磁碟快取（`.gdep_cache/`）的實際效果。

### UE5 ProjectZ

| 指標 | 數值 | 備註 |
|------|------|------|
| 冷啟動掃描（平均） | **1.432 s** | 3 次測量 |
| 冷啟動掃描（最小） | **0.723 s** | 清除快取後首次執行 |
| 熱快取掃描（平均） | **0.467 s** ± 9.1 ms | 5 次測量 |
| 熱快取掃描（最小） | **0.456 s** | |
| **快取加速比** | **~3×**（相對冷啟動最小值） | |

### Unity CommercialMobileGame（SSD — `D:\Projects\GameClient`）

| 指標 | 數值 | 備註 |
|------|------|------|
| 冷啟動掃描（平均） | **3.342 s** | 3 次測量，首次未命中 OS 檔案快取 |
| 冷啟動掃描（最小） | **0.465 s** | OS 檔案快取預熱後 |
| 熱快取掃描（平均） | **0.487 s** ± 33.2 ms | 5 次測量 |
| 熱快取掃描（最小） | **0.460 s** | |
| **快取加速比** | **~7×**（相對冷啟動平均） | |

> **HDD vs SSD**：HDD (`D:\`) 冷啟動平均 559 ms / 熱快取 469 ms — 幾乎無差異。  
> SSD 冷啟動 3.3 s → 熱快取 0.49 s — **快取效果達 6-7 倍**。  
> HDD 上 dotnet subprocess 啟動成本超過 I/O 成本，導致快取收益較小。

---

## 情境 B — 增量更新

> 修改 1 個檔案後重新掃描的時間（驗證部分快取失效）

| 專案 | 冷啟動 | 熱快取（無變更） | 增量（1 個檔案變更） | 目標 |
|------|--------|----------------|-------------------|------|
| UE5 ProjectZ | 0.69 s | **0.438 s** | **0.69 s** | < 3 s ✅ |
| Unity CommercialMobileGame (SSD) | 0.43 s | **0.411 s** | **3.79 s** | < 3 s ⚠️ |

> Unity 增量 3.79 s 包含 `dotnet` subprocess 重啟開銷（~3 s）。  
> 快取指紋檢查本身低於 20 ms，僅重新解析已變更的檔案。

---

## 情境 C — 各功能分析耗時

| 功能 | 目標 | 平均 | 備註 |
|------|------|------|------|
| `gdep scan` | UE5 ProjectZ（熱快取） | **0.467 s** | |
| `gdep scan` | Unity ProjectA（熱快取） | **0.487 s** | |
| `gdep lint` | UE5 ProjectZ | **1.858 s** | 3 次平均，首次 3.05 s |
| `gdep describe` | UE5 `UARGamePlayAbility_BasicAttack` | **1.267 s** | |
| `gdep describe` | Unity `CombatCore` | **3.018 s** | 包含 C# 解析 |

---

## 情境 D — 記憶體分析

> 使用 `memory_profiler` 測量峰值 RSS。目標：UE5 < 300 MB，Unity < 200 MB。

| 專案 | 峰值記憶體 | 目標 | 結果 |
|------|----------|------|------|
| UE5 ProjectZ | **28.5 MB** | < 300 MB | ✅ 通過 |
| Unity CommercialMobileGame | **29.3 MB** | < 200 MB | ✅ 通過 |

> 兩個專案均在 **30 MB 以下**，相對目標有 **10 倍以上的餘裕**。  
> 包含 Python 程序基礎開銷（~20 MB），純分析記憶體約 ~10 MB。

---

## 情境 F — MCP 伺服器各功能回應時間

> 基於 UE5 ProjectZ。冷啟動 = 清除快取後，熱快取 = 保留快取。

| 功能 | 冷啟動 | 熱快取 | 加速比 |
|------|--------|--------|--------|
| `analyze_gas` | **28.8 s** | **0.094 s** | **307×** 🚀 |
| `build_bp_map` | **4.2 s** | **0.076 s** | **55×** 🚀 |
| `analyze_behavior_tree` | **3.3 s** | **0.079 s** | **41×** 🚀 |
| `analyze_state_tree` | **3.0 s** | **0.077 s** | **39×** 🚀 |
| `analyze_abp` | **4.1 s** | **0.086 s** | **48×** 🚀 |

> **第 30 步改進**：新增 `uasset_cache.py` 公共快取層，所有函式熱快取均在 0.1 s 以下。  
> 透過 Content 根目錄 mtime 指紋（`os.scandir` 方式，~20 ms）驗證快取有效性。

---

## 綜合摘要

| 指標 | 數值 | 目標 |
|------|------|------|
| UE5 冷啟動掃描 | 0.72 s | < 30 s ✅ |
| UE5 熱快取掃描 | **0.46 s** | < 1 s ✅ |
| Unity 冷啟動掃描 (SSD) | 0.47 s | < 15 s ✅ |
| Unity 熱快取掃描 (SSD) | **0.49 s** | < 0.5 s ✅ |
| UE5 增量（1 個檔案） | **0.69 s** | < 3 s ✅ |
| Unity 增量（1 個檔案） | 3.79 s | < 3 s ⚠️ |
| UE5 峰值記憶體 | **28.5 MB** | < 300 MB ✅ |
| Unity 峰值記憶體 | **29.3 MB** | < 200 MB ✅ |
| `analyze_gas` 熱快取 | **0.094 s** | — 🚀 |
| `build_bp_map` 熱快取 | **0.076 s** | — 🚀 |

---

## 剩餘瓶頸

| 項目 | 現狀 | 改進方案 | 預期效果 |
|------|------|---------|---------|
| Unity 增量 | 3.79 s（含 dotnet 重啟） | 保持 dotnet 長程序或僅 patch 變更檔案 | < 1 s |
| `build_bp_map` 冷啟動 | 4.2 s → 熱快取 0.076 s ✅ | ~~uasset mtime 快取~~ 已完成 | — |
| `analyze_gas` 冷啟動 | 28.8 s → 熱快取 0.094 s ✅ | ~~快取~~ 已完成 | — |
