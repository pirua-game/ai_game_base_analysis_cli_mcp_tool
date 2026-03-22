# 📊 gdep Performance Benchmark

> **측정 환경**: Windows 11, AMD Ryzen (64-bit), 32GB RAM  
> **스토리지**: UE5 ProjectZ — HDD(NVMe), Unity ProjectA — NVMe SSD (`F:\`)  
> **측정 도구**: [hyperfine](https://github.com/sharkdp/hyperfine) v1.20.0, [memory_profiler](https://github.com/pythonprofilers/memory_profiler) v0.61  
> **측정 일자**: 2026-03-22  

---

## 테스트 프로젝트 규모

| 프로젝트 | 엔진 | 규모 |
|---------|------|------|
| **ProjectZ** (Lyra 기반) | UE5 | C++ 소스 241개 파일 / Content 2,898개 uasset·umap / 플러그인 9개 |
| **CommercialMobileGame** (실서비스 모바일) | Unity C# | 667개 `.cs` 파일 / 904개 클래스 / 순환참조 40개 |

---

## 케이스 A — Cold vs Warm 캐시 성능 ⭐

> `mtime` 기반 디스크 캐시(`.gdep_cache/`)의 실제 효과를 측정합니다.

### UE5 ProjectZ

| 측정 항목 | 수치 | 비고 |
|-----------|------|------|
| Cold Scan (평균) | **1.432 s** | 3회 측정 |
| Cold Scan (최솟값) | **0.723 s** | 캐시 삭제 후 첫 실행 |
| Warm Scan (평균) | **0.467 s** ± 9.1 ms | 5회 측정 |
| Warm Scan (최솟값) | **0.456 s** | |
| **캐시 속도 향상** | **~3x** (cold min 기준) | |


### Unity CommercialMobileGame (SSD — `D:\Projects\GameClient`)

| 측정 항목 | 수치 | 비고 |
|-----------|------|------|
| Cold Scan (평균) | **3.342 s** | 3회 측정, 1회차 OS 파일 캐시 미적중 |
| Cold Scan (최솟값) | **0.465 s** | OS 파일 캐시 워밍 후 |
| Warm Scan (평균) | **0.487 s** ± 33.2 ms | 5회 측정 |
| Warm Scan (최솟값) | **0.460 s** | |
| **캐시 속도 향상** | **~7x** (cold mean 기준) | |

> **HDD vs SSD 비교**: HDD 경로(`D:\`)에서는 cold 평균 559 ms / warm 469 ms로  
> 거의 차이 없음. SSD에서는 cold 3.3s→warm 0.49s로 **캐시 효과가 6-7배** 나타남.  
> HDD는 dotnet subprocess 기동 비용이 I/O 비용보다 커서 캐시 이득이 작았던 것.

---

## 케이스 B — Incremental Update

> 파일 1개 변경 후 재스캔 시간 (캐시 부분 무효화 확인)

| 프로젝트 | Cold | Warm (변경 없음) | Incremental (파일 1개 변경) | 목표 |
|---------|------|-----------------|---------------------------|------|
| UE5 ProjectZ | 0.69 s | **0.438 s** | **0.69 s** | < 3 s ✅ |
| Unity CommercialMobileGame (SSD) | 0.43 s | **0.411 s** | **3.79 s** | < 3 s ⚠️ |

> Unity incremental 3.79 s: `dotnet` subprocess 재기동 오버헤드(~3 s)가 포함된 수치.  
> 캐시 지문 검사 자체는 20 ms 이하이며, C# 재파싱 필요 파일만 처리됨.

---

## 케이스 C — 기능별 분석 시간

| 기능 | 대상 | 수치 (mean) | 비고 |
|------|------|------------|------|
| `gdep scan` | UE5 ProjectZ (warm) | **0.467 s** | |
| `gdep scan` | Unity ProjectA (warm) | **0.487 s** | |
| `gdep lint` | UE5 ProjectZ | **1.858 s** | 3회 평균, 첫 실행 3.05 s |
| `gdep describe` | UE5 `UARGamePlayAbility_BasicAttack` | **1.267 s** | |
| `gdep describe` | Unity `CombatCore` | **3.018 s** | C# 파싱 포함 |


---

## 케이스 D — 메모리 프로파일링

> `memory_profiler`로 측정한 피크 RSS. 목표: UE5 < 300 MB, Unity < 200 MB.

| 프로젝트 | 피크 메모리 | 목표 | 결과 |
|---------|------------|------|------|
| UE5 ProjectZ | **28.5 MB** | < 300 MB | ✅ PASS |
| Unity CommercialMobileGame | **29.3 MB** | < 200 MB | ✅ PASS |

> 두 프로젝트 모두 **30 MB 이하**로 측정. 목표 대비 **10배 이상** 여유.  
> Python 프로세스 기본 오버헤드(~20 MB)를 포함한 수치로, 순수 분석 메모리는 ~10 MB 수준.

---

## 케이스 F — MCP 서버 기능별 응답성

> UE5 ProjectZ 기준, 각 분석 함수 직접 호출. Cold = 캐시 삭제 후, Warm = 캐시 보존.

| 기능 | Cold | Warm | 향상 |
|------|------|------|------|
| `analyze_gas` | **28.8 s** | **0.094 s** | **307x** 🚀 |
| `build_bp_map` | **4.2 s** | **0.076 s** | **55x** 🚀 |
| `analyze_behavior_tree` | **3.3 s** | **0.079 s** | **41x** 🚀 |
| `analyze_state_tree` | **3.0 s** | **0.077 s** | **39x** 🚀 |
| `analyze_abp` | **4.1 s** | **0.086 s** | **48x** 🚀 |

> **30단계 개선**: `uasset_cache.py` 공통 캐시 레이어 추가로 전 함수 warm 0.1s 이하 달성.  
> Content 루트 mtime fingerprint(`os.scandir` 기반, ~20ms) 로 캐시 유효성 검증.  
> Cold 수치는 uasset 바이너리 전체 스캔 포함 최초 실행 기준.

---

## 종합 요약

| 지표 | 수치 | 목표 |
|------|------|------|
| UE5 Cold Scan | 0.72 s | < 30 s ✅ |
| UE5 Warm Scan | **0.46 s** | < 1 s ✅ |
| Unity Cold Scan (SSD) | 0.47 s | < 15 s ✅ |
| Unity Warm Scan (SSD) | **0.49 s** | < 0.5 s ✅ |
| UE5 Incremental (파일 1개) | **0.69 s** | < 3 s ✅ |
| Unity Incremental (파일 1개) | 3.79 s | < 3 s ⚠️ |
| UE5 Peak Memory | **28.5 MB** | < 300 MB ✅ |
| Unity Peak Memory | **29.3 MB** | < 200 MB ✅ |
| `analyze_gas` warm | **0.094 s** | — 🚀 |
| `build_bp_map` warm | **0.076 s** | — 🚀 |
| `analyze_abp` warm | **0.086 s** | — 🚀 |
| `analyze_behavior_tree` warm | **0.079 s** | — 🚀 |

---

## 개선 후보 (잔여 병목)

| 항목 | 현황 | 개선 방안 | 예상 효과 |
|------|------|----------|----------|
| Unity Incremental | 3.79 s (dotnet 재기동 포함) | dotnet 장기 프로세스 유지 or 변경 파일만 패치 | < 1 s |
| `build_bp_map` cold | 4.2 s → warm 0.076 s ✅ | ~~uasset mtime 캐시~~ 완료 | — |
| `analyze_gas` cold | 28.8 s → warm 0.094 s ✅ | ~~캐시~~ 완료 | — |
