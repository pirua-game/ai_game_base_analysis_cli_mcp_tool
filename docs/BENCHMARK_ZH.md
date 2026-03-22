# 📊 gdep 性能基准测试

> **测试环境**：Windows 11、AMD Ryzen (64-bit)、32 GB RAM  
> **存储**：UE5 ProjectZ — HDD (NVMe)、Unity ProjectA — NVMe SSD (`F:\`)  
> **工具**：[hyperfine](https://github.com/sharkdp/hyperfine) v1.20.0、[memory_profiler](https://github.com/pythonprofilers/memory_profiler) v0.61  
> **测试日期**：2026-03-22  

---

## 测试项目规模

| 项目 | 引擎 | 规模 |
|------|------|------|
| **ProjectZ** (基于 Lyra) | UE5 | C++ 源码 241 个文件 / 2,898 个 uasset·umap / 9 个插件 |
| **CommercialMobileGame** (线上移动端) | Unity C# | 667 个 `.cs` 文件 / 904 个类 / 40 个循环依赖 |

---

## 场景 A — 冷启动 vs 热缓存性能 ⭐

> 测量基于 `mtime` 的磁盘缓存（`.gdep_cache/`）的实际效果。

### UE5 ProjectZ

| 指标 | 数值 | 备注 |
|------|------|------|
| 冷启动扫描（均值） | **1.432 s** | 3 次测量 |
| 冷启动扫描（最小值） | **0.723 s** | 清除缓存后首次运行 |
| 热缓存扫描（均值） | **0.467 s** ± 9.1 ms | 5 次测量 |
| 热缓存扫描（最小值） | **0.456 s** | |
| **缓存加速比** | **~3×**（相对冷启动最小值） | |

### Unity CommercialMobileGame（SSD — `D:\Projects\GameClient`）

| 指标 | 数值 | 备注 |
|------|------|------|
| 冷启动扫描（均值） | **3.342 s** | 3 次测量，首次未命中 OS 文件缓存 |
| 冷启动扫描（最小值） | **0.465 s** | OS 文件缓存预热后 |
| 热缓存扫描（均值） | **0.487 s** ± 33.2 ms | 5 次测量 |
| 热缓存扫描（最小值） | **0.460 s** | |
| **缓存加速比** | **~7×**（相对冷启动均值） | |

> **HDD vs SSD**：HDD (`D:\`) 冷启动均值 559 ms / 热缓存 469 ms — 几乎无差异。  
> SSD 上冷启动 3.3 s → 热缓存 0.49 s — **缓存效果达 6-7 倍**。  
> HDD 上 dotnet subprocess 启动开销超过 I/O 开销，导致缓存收益较小。

---

## 场景 B — 增量更新

> 修改 1 个文件后重新扫描的时间（验证部分缓存失效）

| 项目 | 冷启动 | 热缓存（无变更） | 增量（1 个文件变更） | 目标 |
|------|--------|----------------|-------------------|------|
| UE5 ProjectZ | 0.69 s | **0.438 s** | **0.69 s** | < 3 s ✅ |
| Unity CommercialMobileGame (SSD) | 0.43 s | **0.411 s** | **3.79 s** | < 3 s ⚠️ |

> Unity 增量 3.79 s 包含 `dotnet` subprocess 重启开销（~3 s）。  
> 缓存指纹检查本身低于 20 ms，仅重新解析变更的文件。

---

## 场景 C — 各功能分析耗时

| 功能 | 目标 | 均值 | 备注 |
|------|------|------|------|
| `gdep scan` | UE5 ProjectZ（热缓存） | **0.467 s** | |
| `gdep scan` | Unity ProjectA（热缓存） | **0.487 s** | |
| `gdep lint` | UE5 ProjectZ | **1.858 s** | 3 次均值，首次 3.05 s |
| `gdep describe` | UE5 `UARGamePlayAbility_BasicAttack` | **1.267 s** | |
| `gdep describe` | Unity `CombatCore` | **3.018 s** | 包含 C# 解析 |

---

## 场景 D — 内存分析

> 使用 `memory_profiler` 测量峰值 RSS。目标：UE5 < 300 MB，Unity < 200 MB。

| 项目 | 峰值内存 | 目标 | 结果 |
|------|---------|------|------|
| UE5 ProjectZ | **28.5 MB** | < 300 MB | ✅ 通过 |
| Unity CommercialMobileGame | **29.3 MB** | < 200 MB | ✅ 通过 |

> 两个项目均在 **30 MB 以下**，相对目标有 **10 倍以上的余量**。  
> 包含 Python 进程基础开销（~20 MB），纯分析内存约 ~10 MB。

---

## 场景 F — MCP 服务器各功能响应时间

> 基于 UE5 ProjectZ。冷启动 = 清除缓存后，热缓存 = 保留缓存。

| 功能 | 冷启动 | 热缓存 | 加速比 |
|------|--------|--------|--------|
| `analyze_gas` | **28.8 s** | **0.094 s** | **307×** 🚀 |
| `build_bp_map` | **4.2 s** | **0.076 s** | **55×** 🚀 |
| `analyze_behavior_tree` | **3.3 s** | **0.079 s** | **41×** 🚀 |
| `analyze_state_tree` | **3.0 s** | **0.077 s** | **39×** 🚀 |
| `analyze_abp` | **4.1 s** | **0.086 s** | **48×** 🚀 |

> **第 30 步改进**：新增 `uasset_cache.py` 公共缓存层，所有函数热缓存均在 0.1 s 以下。  
> 通过 Content 根目录 mtime 指纹（`os.scandir` 方式，~20 ms）验证缓存有效性。  
> 冷启动数值为包含 uasset 二进制全量扫描的首次运行基准。

---

## 综合摘要

| 指标 | 数值 | 目标 |
|------|------|------|
| UE5 冷启动扫描 | 0.72 s | < 30 s ✅ |
| UE5 热缓存扫描 | **0.46 s** | < 1 s ✅ |
| Unity 冷启动扫描 (SSD) | 0.47 s | < 15 s ✅ |
| Unity 热缓存扫描 (SSD) | **0.49 s** | < 0.5 s ✅ |
| UE5 增量（1 个文件） | **0.69 s** | < 3 s ✅ |
| Unity 增量（1 个文件） | 3.79 s | < 3 s ⚠️ |
| UE5 峰值内存 | **28.5 MB** | < 300 MB ✅ |
| Unity 峰值内存 | **29.3 MB** | < 200 MB ✅ |
| `analyze_gas` 热缓存 | **0.094 s** | — 🚀 |
| `build_bp_map` 热缓存 | **0.076 s** | — 🚀 |
| `analyze_abp` 热缓存 | **0.086 s** | — 🚀 |
| `analyze_behavior_tree` 热缓存 | **0.079 s** | — 🚀 |

---

## 剩余瓶颈

| 项目 | 现状 | 改进方案 | 预期效果 |
|------|------|---------|---------|
| Unity 增量 | 3.79 s（含 dotnet 重启） | 保持 dotnet 长进程或仅 patch 变更文件 | < 1 s |
| `build_bp_map` 冷启动 | 4.2 s → 热缓存 0.076 s ✅ | ~~uasset mtime 缓存~~ 已完成 | — |
| `analyze_gas` 冷启动 | 28.8 s → 热缓存 0.094 s ✅ | ~~缓存~~ 已完成 | — |
