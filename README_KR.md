# 🎮 gdep — 게임 코드베이스 분석 도구

**Unity · UE5 · Axmol 대형 프로젝트를 0.5초 만에 파악하고, Claude / Cursor가 실제 코드를 읽게 만드는 도구**

[![CI](https://github.com/pirua-game/gdep/actions/workflows/ci.yml/badge.svg)](https://github.com/pirua-game/gdep/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/gdep)](https://pypi.org/project/gdep/)
[![npm](https://img.shields.io/npm/v/gdep-mcp)](https://www.npmjs.com/package/gdep-mcp)

> *"이 클래스 수정하면 어디까지 영향 가?"* — 3초 만에 정확히 답변, 환각 0건
> 실측: **MCP 정확도 100% (5/5)** — 코드 기반 사실 vs 일반 Claude 추측 + 환각

**다른 언어로 읽기:**
[English](./README.md) · [日本語](./README_JA.md) · [简体中文](./README_ZH.md) · [繁體中文](./README_ZH_TW.md)

---

## ✨ 왜 gdep를 써야 할까?

대형 게임 클라이언트는 고통입니다:

- UE5 Blueprint 300개 이상 → *"이 Ability가 어디서 호출되나?"* 찾는 데 하루 소요
- Unity Manager 50개 + Prefab 참조 → 리팩토링하다가 순환참조 폭발
- *"이 클래스 수정하면 어디까지 깨지나?"* → 파일 열어서 30분 수동 추적

**gdep는 이 모든 걸 0.5초 만에 해결합니다.**

### 실측 성능 지표

| 지표 | 수치 | 비고 |
|------|------|------|
| UE5 warm scan | **0.46초** | uasset 2,800개 이상 프로젝트 |
| Unity warm scan | **0.49초** | SSD 환경, 클래스 900개 이상 |
| 피크 메모리 | **28.5 MB** | 목표 대비 10배 여유 |
| MCP 정확도 | **5/5 (100%)** | 코드 기반 사실 |

> 상세 → [docs/BENCHMARK_KR.md](./docs/BENCHMARK_KR.md) · [docs/mcp-benchmark_KR.md](./docs/mcp-benchmark_KR.md)

---

## 🤖 MCP 통합 — AI가 실제 코드를 읽게 만드는 핵심

gdep는 Claude Desktop, Cursor 등 MCP 호환 AI Agent를 위한 MCP 서버를 제공합니다.

### 1줄 설치

```bash
npm install -g gdep-mcp
```

### AI Agent 설정 (복붙 3줄)

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

설정 끝. 이제 Claude · Cursor · Gemini가 대화마다 게임 엔진 특화 **19개** 도구를 사용할 수 있습니다.

### MCP가 바꾸는 것

```
일반 Claude: "CombatCore는 Manager 계열 의존성이 있을 것 같습니다..." ← 추측
gdep MCP:   직접 의존 2개 · 간접 200개 이상 UI 클래스 · 에셋: prefabs/UI/combat.prefab
```

### 19개 MCP 도구 한눈에 보기

| 도구 | 언제 사용 |
|------|----------|
| `get_project_context` | **항상 가장 먼저** — 전체 프로젝트 개요 |
| `analyze_impact_and_risk` | 클래스 수정 전 안전성 확인 (`detail_level="summary"`로 빠른 요약 가능) |
| `explain_method_logic` | 단일 메서드 내부 제어 흐름 요약 (Guard/Branch/Loop/Always) |
| `trace_gameplay_flow` | C++ → Blueprint 호출 체인 추적 |
| `inspect_architectural_health` | 기술 부채 전체 진단 |
| `explore_class_semantics` | 낯선 클래스 상세 분석 |
| `suggest_test_scope` | 클래스 수정 후 실행해야 할 테스트 파일 자동 산정 |
| `suggest_lint_fixes` | lint 이슈 + 코드 수정 제안 (dry-run) |
| `summarize_project_diff` | git diff 결과를 아키텍처 관점으로 요약 |
| `get_architecture_advice` | 프로젝트 종합 진단 + LLM 아키텍처 어드바이스 |
| `execute_gdep_cli` | CLI 전 기능 직접 접근 |
| `find_unity_event_bindings` | Inspector 연결 메서드 (코드 검색 불가 영역) |
| `analyze_unity_animator` | Animator 상태머신 구조 |
| `analyze_axmol_events` | Axmol EventDispatcher/Scheduler 바인딩 맵 |
| `analyze_ue5_gas` | GAS Ability / Effect / Tag / ASC 전체 — **신뢰도 헤더** + IS-A 에셋 역할 구분 포함 |
| `analyze_ue5_behavior_tree` | BehaviorTree 에셋 구조 |
| `analyze_ue5_state_tree` | StateTree 에셋 구조 |
| `analyze_ue5_animation` | ABP 상태 + Montage + GAS Notify |
| `analyze_ue5_blueprint_mapping` | C++ 클래스 → Blueprint 구현체 매핑 — **신뢰도 헤더** 포함 |

### UE5 신뢰도 투명화

`analyze_ue5_gas`와 `analyze_ue5_blueprint_mapping`은 모든 응답 상단에 신뢰도 헤더를 출력합니다:

```
> Analysis method: cpp_source_regex + binary_pattern_match
> Confidence: **MEDIUM**
> Coverage: 4633/4633 assets parsed (100.0%)
> UE version: 5.6 (validated)
```

`gdep init`으로 생성된 `.gdep/AGENTS.md`는 AI 에이전트에게 신뢰 등급별 행동 가이드를 제공합니다 (HIGH=신뢰, MEDIUM=신뢰 가능, LOW=소스 확인).

> 상세 설정 → [gdep-cli/gdep_mcp/README_KR.md](./gdep-cli/gdep_mcp/README_KR.md)

---

## 📦 설치

**사전 요구사항**

| 항목 | 버전 | 용도 |
|------|------|------|
| Python | 3.11+ | CLI · MCP 서버 |
| .NET Runtime | 8.0+ | C# / Unity 프로젝트 분석 |

### 원클릭 설치 (권장)

```bash
# Windows
install.bat

# macOS / Linux
chmod +x install.sh && ./install.sh
```

### 수동 설치

```bash
cd gdep-cli && pip install -e .
```

---

## 🚀 빠른 시작

```bash
gdep detect {경로}                          # 엔진 자동 감지
gdep scan {경로} --circular --top 15        # 구조 분석
gdep init {경로}                            # AI Agent용 .gdep/AGENTS.md 생성
gdep advise {경로}                          # 아키텍처 진단 + 어드바이스
```

`gdep init` 실행 후 Claude · Cursor · Gemini가 프로젝트 컨텍스트를 자동으로 읽고
어떤 질문에 어떤 gdep 도구를 써야 하는지 스스로 판단합니다.

---

## 🖥️ Web UI — 브라우저에서 시각적으로 분석하기

설치 후 터미널 없이 브라우저에서 의존성 그래프, 호출 흐름, AI 채팅을 사용할 수 있습니다.

**1단계 — 설치** (프로젝트 루트에서 최초 1회)

```
install.bat          # Windows
./install.sh         # macOS / Linux
```

**2단계 — 실행**

```
run.bat              # Windows — 백엔드 + 프론트엔드를 별도 터미널 2개로 자동 실행
./run.sh             # macOS/Linux — 터미널 1: 백엔드  (http://localhost:8000)
./run_front.sh       # macOS/Linux — 터미널 2: 프론트엔드 (http://localhost:5173)
```

`http://localhost:5173` 접속 → 사이드바에서 프로젝트 소스 폴더 지정

주요 기능:
- 인터랙티브 의존성 그래프 · 호출 흐름 시각화
- 클래스 브라우저 (영향 분석 · 린트 포함)
- 실제 코드를 읽는 AI 채팅 에이전트 (툴 콜링)
- 엔진 전용 탐색기: GAS · Blueprint 매핑 · Animator · BehaviorTree · StateTree

> UI 지원 언어: **영어(English) 및 한국어** 2개만 지원 · 로컬 LLM: **Ollama** 사용 가능 · 상용 프로그램이 아니므로 일부 기능이 완벽하지 않을 수 있습니다

상세 문서 → [gdep-cli/web/README_KR.md](./gdep-cli/web/README_KR.md)

---

## 🎯 커맨드 레퍼런스

| 커맨드 | 요약 | 언제 사용 |
|--------|------|----------|
| `detect` | 엔진 자동 감지 | 첫 분석 전 |
| `scan` | 결합도 · 순환참조 · 데드코드 | 구조 파악, 리팩토링 전 |
| `describe` | 클래스 상세 + Blueprint 구현체 + AI 요약 | 낯선 클래스, 코드 리뷰 |
| `flow` | 메서드 호출 체인 (C++→BP 경계) | 버그 추적, 흐름 분석 |
| `impact` | 변경 파급 역추적 | 리팩토링 전 안전성 확인 |
| `test-scope` | 클래스 수정 후 실행할 테스트 파일 산정 | 머지 전, CI 계획 |
| `watch` | 실시간 파일 변경 감시 (impact+test+lint) | 개발 중 상시 모니터링 |
| `lint` | 게임 특화 안티패턴 스캔 (+ `--fix`) | PR 전 품질 체크 |
| `advise` | 전체 아키텍처 진단 + LLM 어드바이스 | 아키텍처 리뷰, 기술 부채 |
| `graph` | 의존성 그래프 내보내기 | 문서화, 시각화 |
| `diff` | 커밋 전후 의존성 비교 | PR 리뷰, CI 게이트 |
| `init` | AI Agent 컨텍스트 파일 생성 | **AI 코딩 어시스턴트 최초 설정** |
| `context` | 프로젝트 컨텍스트 출력 | AI 채팅 복붙용 |
| `hints` | 싱글톤 힌트 관리 | 흐름 정확도 향상 |
| `config` | LLM 설정 | AI 요약 기능 사용 전 |


## 📖 커맨드 상세

### scan

```bash
gdep scan {경로} [옵션]
```

| 옵션 | 설명 |
|------|------|
| `--circular` | 순환참조 감지 |
| `--dead-code` | 미참조 클래스 감지 |
| `--deep` | 메서드 본문 포함 심화 분석 |
| `--include-refs` | Prefab/Blueprint 역참조 포함 |
| `--top N` | 결합도 상위 N개 표시 (기본: 20) |
| `--format json` | JSON 출력 (CI/Agent용) |

### flow — C++ → Blueprint 경계 자동 추적

```bash
gdep flow {경로} --class <클래스> --method <메서드> [--depth N]
```

```
└── UARGamePlayAbility_BasicAttack.ActivateAbility
    ├── CommitAbility ○
    ├── BP_GA_BasicAttack_C.K2_ActivateAbility ○ [BP]   ← Blueprint 진입점
    └── BP_GA_HeavyAttack_C.K2_ActivateAbility ○ [BP]
```

### test-scope — 클래스 수정 후 실행할 테스트 파일 산정

```bash
gdep test-scope {경로} <클래스명>
gdep test-scope {경로} <클래스명> --format json   # CI 파이프라인용
gdep test-scope {경로} <클래스명> --depth 5       # 더 넓은 탐색 범위
```

### watch — 실시간 파일 변경 감시

```bash
gdep watch {경로}                          # 프로젝트 전체 감시
gdep watch {경로} --class CombatManager    # 특정 클래스 관련 파일만 감시
gdep watch {경로} --debounce 2.0           # 연속 저장 대기 시간 조정
```

파일 저장마다 즉시 출력: 영향 클래스 수 · 테스트 파일 수 · lint 경고.

### advise — 아키텍처 진단

```bash
gdep advise {경로}                          # 전체 프로젝트 진단
gdep advise {경로} --focus CombatManager    # 특정 클래스 중심 진단
gdep advise {경로} --format json            # CI/MCP 출력용
```

LLM 미설정 시: 데이터 기반 구조화 리포트 (cycles/coupling/dead-code/lint).
LLM 설정 시: IMMEDIATE / MID-TERM / LONG-TERM 자연어 어드바이스.

### lint — 게임 엔진 특화 안티패턴 16개

```bash
gdep lint {경로}                # 스캔
gdep lint {경로} --fix          # 스캔 + 코드 수정 제안 (dry-run, 파일 미수정)
```

| Rule ID | 엔진 | 설명 |
|---------|------|------|
| `UNI-PERF-001` | Unity | Update 내 GetComponent/Find |
| `UNI-PERF-002` | Unity | Update 내 new/Instantiate |
| `UNI-ASYNC-001` | Unity | Coroutine while(true) yield 없음 |
| `UNI-ASYNC-002` | Unity | Coroutine 내 FindObjectOfType/Resources.Load |
| `UE5-PERF-001` | UE5 | Tick 내 SpawnActor/LoadObject |
| `UE5-PERF-002` | UE5 | BeginPlay 내 동기 LoadObject |
| `UE5-BASE-001` | UE5 | Super:: 호출 누락 |
| `UE5-GAS-001` | UE5 | ActivateAbility() 내 CommitAbility() 누락 |
| `UE5-GAS-002` | UE5 | GAS Ability 내 고비용 world 쿼리 |
| `UE5-GAS-003` | UE5 | BlueprintCallable 10개 초과 |
| `UE5-GAS-004` | UE5 | BlueprintPure에 const 누락 |
| `UE5-NET-001` | UE5 | Replicated 속성에 ReplicatedUsing 콜백 없음 |
| `AXM-PERF-001` | Axmol | update() 내 getChildByName/Tag 호출 |
| `AXM-MEM-001` | Axmol | retain() 후 release() 누락 |
| `AXM-EVENT-001` | Axmol | addEventListenerWith* 후 removeEventListener 누락 |
| `GEN-ARCH-001` | 공통 | 순환 참조 |

---

## 🎮 지원 엔진

| 엔진 | 클래스 분석 | 흐름 분석 | 역참조 | 특화 기능 |
|------|------------|----------|--------|----------|
| Unity (C#) | ✅ | ✅ | ✅ Prefab/Scene | UnityEvent, Animator |
| Unreal Engine 5 | ✅ UCLASS/USTRUCT/UENUM | ✅ C++→BP | ✅ Blueprint/Map | GAS, BP 매핑, BT/ST, ABP/Montage |
| Axmol / Cocos2d-x (C++) | ✅ Tree-sitter | ✅ | — | EventDispatcher/Scheduler 바인딩 |
| .NET (C#) | ✅ | ✅ | — | |
| Generic C++ | ✅ | ✅ | — | |

---

## 🔄 대표 워크플로우

### 낯선 코드베이스 온보딩

```bash
gdep init {경로}
gdep scan {경로} --circular --top 20
gdep describe {경로} CombatManager --summarize
gdep flow {경로} --class CombatManager --method ExecuteAction
```

### UE5 GAS end-to-end 흐름 파악

```bash
gdep describe {경로} UARGameplayAbility_Dash
gdep flow {경로} --class UARGameplayAbility_Dash --method ActivateAbility
```

### 리팩토링 전 안전성 확인

```bash
gdep impact {경로} CombatCore --depth 5
gdep test-scope {경로} CombatCore
gdep lint {경로} --fix
gdep diff {경로} --commit HEAD
```

### 아키텍처 리뷰

```bash
gdep advise {경로}
gdep advise {경로} --focus BattleManager
```

### CI 품질 게이트

```bash
gdep diff . --commit HEAD~1 --fail-on-cycles
gdep lint . --format json > lint_report.json
gdep test-scope . ChangedClass --format json > test_scope.json
```

### 개발 중 실시간 피드백

```bash
gdep watch {경로} --class CombatManager
# → 파일 저장마다: 영향 클래스 수 · 테스트 파일 수 · lint 경고
```

---

## ⚙️ C# 파서 (`gdep.dll`)

**OS 독립적 단일 DLL** — Windows · macOS · Linux 동일 동작.

```bash
dotnet publish -c Release --no-self-contained -o publish_dll
```

탐지 우선순위: `$GDEP_DLL` env → `publish_dll/gdep.dll` → `publish/gdep.dll` → 레거시 바이너리

---

*MCP 서버 설정 → [gdep-cli/gdep_mcp/README_KR.md](./gdep-cli/gdep_mcp/README_KR.md)*
*CI/CD 통합 → [docs/ci-integration_KR.md](./docs/ci-integration_KR.md)*
*성능 벤치마크 → [docs/BENCHMARK_KR.md](./docs/BENCHMARK_KR.md)*
*MCP 토큰·정확도 비교 → [docs/mcp-benchmark_KR.md](./docs/mcp-benchmark_KR.md)*
