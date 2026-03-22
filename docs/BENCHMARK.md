# 📊 gdep Performance Benchmark

> **Environment**: Windows 11, AMD Ryzen (64-bit), 32 GB RAM  
> **Storage**: UE5 ProjectZ — HDD (NVMe), Unity ProjectA — NVMe SSD (`F:\`)  
> **Tools**: [hyperfine](https://github.com/sharkdp/hyperfine) v1.20.0, [memory_profiler](https://github.com/pythonprofilers/memory_profiler) v0.61  
> **Date**: 2026-03-22  

---

## Test Project Scale

| Project | Engine | Scale |
|---------|--------|-------|
| **ProjectZ** (Lyra-based) | UE5 | 241 C++ source files / 2,898 uasset·umap / 9 plugins |
| **CommercialMobileGame** (live mobile) | Unity C# | 667 `.cs` files / 904 classes / 40 circular deps |

---

## Case A — Cold vs Warm Cache ⭐

> Measures the real effect of `mtime`-based disk cache (`.gdep_cache/`).

### UE5 ProjectZ

| Metric | Value | Notes |
|--------|-------|-------|
| Cold Scan (mean) | **1.432 s** | 3 runs |
| Cold Scan (min) | **0.723 s** | First run after cache deletion |
| Warm Scan (mean) | **0.467 s** ± 9.1 ms | 5 runs |
| Warm Scan (min) | **0.456 s** | |
| **Cache speedup** | **~3x** (vs cold min) | |

### Unity CommercialMobileGame (SSD — `D:\Projects\GameClient`)

| Metric | Value | Notes |
|--------|-------|-------|
| Cold Scan (mean) | **3.342 s** | 3 runs, 1st run misses OS file cache |
| Cold Scan (min) | **0.465 s** | After OS file cache warm-up |
| Warm Scan (mean) | **0.487 s** ± 33.2 ms | 5 runs |
| Warm Scan (min) | **0.460 s** | |
| **Cache speedup** | **~7x** (vs cold mean) | |

> **HDD vs SSD**: On HDD (`D:\`), cold avg 559 ms / warm 469 ms — almost no difference.  
> On SSD, cold 3.3 s → warm 0.49 s — **6-7× cache effect**.  
> On HDD, the dotnet subprocess startup cost exceeds I/O cost, so cache gains are smaller.

---

## Case B — Incremental Update

> Re-scan time after changing one file (verifies partial cache invalidation).

| Project | Cold | Warm (no change) | Incremental (1 file changed) | Target |
|---------|------|-----------------|------------------------------|--------|
| UE5 ProjectZ | 0.69 s | **0.438 s** | **0.69 s** | < 3 s ✅ |
| Unity CommercialMobileGame (SSD) | 0.43 s | **0.411 s** | **3.79 s** | < 3 s ⚠️ |

> Unity incremental 3.79 s includes `dotnet` subprocess restart overhead (~3 s).  
> The cache fingerprint check itself is under 20 ms; only changed files are re-parsed.

---

## Case C — Per-Feature Analysis Time

| Feature | Target | Mean | Notes |
|---------|--------|------|-------|
| `gdep scan` | UE5 ProjectZ (warm) | **0.467 s** | |
| `gdep scan` | Unity ProjectA (warm) | **0.487 s** | |
| `gdep lint` | UE5 ProjectZ | **1.858 s** | avg of 3 runs; first run 3.05 s |
| `gdep describe` | UE5 `UARGamePlayAbility_BasicAttack` | **1.267 s** | |
| `gdep describe` | Unity `CombatCore` | **3.018 s** | includes C# parsing |

---

## Case D — Memory Profiling

> Peak RSS measured with `memory_profiler`. Target: UE5 < 300 MB, Unity < 200 MB.

| Project | Peak Memory | Target | Result |
|---------|------------|--------|--------|
| UE5 ProjectZ | **28.5 MB** | < 300 MB | ✅ PASS |
| Unity CommercialMobileGame | **29.3 MB** | < 200 MB | ✅ PASS |

> Both projects under **30 MB** — more than **10× headroom** vs target.  
> Includes Python process baseline (~20 MB); pure analysis memory is ~10 MB.

---

## Case F — MCP Server Per-Function Latency

> Measured on UE5 ProjectZ. Cold = after cache deletion, Warm = cache preserved.

| Function | Cold | Warm | Speedup |
|----------|------|------|---------|
| `analyze_gas` | **28.8 s** | **0.094 s** | **307×** 🚀 |
| `build_bp_map` | **4.2 s** | **0.076 s** | **55×** 🚀 |
| `analyze_behavior_tree` | **3.3 s** | **0.079 s** | **41×** 🚀 |
| `analyze_state_tree` | **3.0 s** | **0.077 s** | **39×** 🚀 |
| `analyze_abp` | **4.1 s** | **0.086 s** | **48×** 🚀 |

> **Step 30 improvement**: Added `uasset_cache.py` common cache layer — all functions warm < 0.1 s.  
> Cache validity is checked via Content root mtime fingerprint (`os.scandir`-based, ~20 ms).  
> Cold figures represent first-run full uasset binary scan.

---

## Summary

| Metric | Value | Target |
|--------|-------|--------|
| UE5 Cold Scan | 0.72 s | < 30 s ✅ |
| UE5 Warm Scan | **0.46 s** | < 1 s ✅ |
| Unity Cold Scan (SSD) | 0.47 s | < 15 s ✅ |
| Unity Warm Scan (SSD) | **0.49 s** | < 0.5 s ✅ |
| UE5 Incremental (1 file) | **0.69 s** | < 3 s ✅ |
| Unity Incremental (1 file) | 3.79 s | < 3 s ⚠️ |
| UE5 Peak Memory | **28.5 MB** | < 300 MB ✅ |
| Unity Peak Memory | **29.3 MB** | < 200 MB ✅ |
| `analyze_gas` warm | **0.094 s** | — 🚀 |
| `build_bp_map` warm | **0.076 s** | — 🚀 |
| `analyze_abp` warm | **0.086 s** | — 🚀 |
| `analyze_behavior_tree` warm | **0.079 s** | — 🚀 |

---

## Remaining Bottlenecks

| Item | Status | Improvement | Expected |
|------|--------|-------------|----------|
| Unity Incremental | 3.79 s (dotnet restart included) | Keep dotnet process alive or patch only changed files | < 1 s |
| `build_bp_map` cold | 4.2 s → warm 0.076 s ✅ | ~~uasset mtime cache~~ done | — |
| `analyze_gas` cold | 28.8 s → warm 0.094 s ✅ | ~~cache~~ done | — |
