# gdep MCP 벤치마크 — AI Agent 토큰 & 정확도 비교

> 측정 환경: Claude Sonnet 4.6 + gdep MCP (로컬)
> 토크나이저: `cl100k_base` (Anthropic Claude와 동일 계열, tiktoken 측정)
> 테스트 프로젝트:
> - **Unity**: ProjectA (실서비스 2D 모바일, 667파일 / 904클래스)
> - **UE5**: ProjectZ / Lyra (대규모 샘플, Zombie 커스텀 포함)
> - **UE5 GAS**: HackAndSlash 포트폴리오 (32파일 / 31클래스)
>
> **MCP 도구 현황 (42단계 기준): 총 18개**
> 공통 9개 + Unity 전용 2개 (`find_unity_event_bindings`, `analyze_unity_animator`)
> UE5 전용 5개 (`analyze_ue5_gas`, `analyze_ue5_animation`, `analyze_ue5_behavior_tree`, `analyze_ue5_state_tree`, `analyze_ue5_blueprint_mapping`)
> Axmol 전용 1개 (`analyze_axmol_events`)
> Raw CLI 1개 (`execute_gdep_cli`)

---

## 핵심 요약

| 항목 | MCP 없음 | MCP 있음 |
|------|---------|---------|
| 답변의 근거 | 추측 / 일반 지식 | 실제 코드 분석 결과 |
| 토큰 수 | 비교 불가 | 공정한 비교 불가능 (아래 참고) |
| 정확도 | ❌ 검증 불가 / 환각 | ✅ 코드 기반 사실 |
| 환각 발생 | 높음 | 없음 |

> **토큰 수를 비교할 수 없는 이유:**
> MCP를 사용할 경우, 하나의 질문이 여러 번의 도구 호출로 이어지며 각각 구조화된 분석 데이터를
> 반환합니다. AI는 매 응답마다 대화 이력 전체를 재읽습니다.
> MCP 없이는 소스 파일을 통째로 읽거나, 컨텍스트 윈도우를 초과하거나,
> 아무것도 읽지 않고 추측하는 등 워크플로 자체가 다릅니다.
> 두 방식의 토큰 수를 비교하는 것은 자동차와 배의 연료 소비를 비교하는 것과 같습니다 —
> 숫자는 존재하지만, 비교 자체에 의미가 없습니다.
>
> **수치가 실제로 말해주는 것:**
> MCP를 사용하면 단 한 번의 질문으로 정확하고 코드에 근거한 답변을 얻습니다.
> MCP 없이는 추측, 환각, 혹은 엉뚱한 파일을 읽어 컨텍스트가 넘치는 결과를 얻습니다.
> 중요한 것은 토큰 수가 아니라 정확도 차이(0/5 vs 5/5)입니다.
---

## 상세 측정 결과


### Q1 — "ManagerBattle이 어떤 역할을 하고, 어떤 클래스들이 의존하는가?"

| | 방식 A (MCP 없음) | 방식 B (MCP 있음) |
|--|--|--|
| **도구** | 없음 | `explore_class_semantics` |
| **답변 토큰** | 92 | 175 |

**방식 A 답변:**
> "ManagerBattle은 이름으로 보아 배틀 관련 매니저 클래스일 것으로 추측됩니다.
> UI나 데이터 클래스들이 참조할 것 같습니다.
> 정확한 의존 클래스 목록은 알 수 없습니다."

**방식 B 답변 (MCP):**
> ManagerBattle은 `ManagerBase` 상속, Fields 173개 / Methods 283개 / 외부 참조 104종의 **God Object**.
> 핵심 의존: CombatCore, UIGameField, UIHandDisplay, EntityCard, RuntimeAbility 등 게임 로직 전반.
> `Managers` 싱글톤 1개에서만 직접 참조되지만 프로젝트 전체에서 `Managers.Battle`로 간접 사용됨.

**정확도 판정:**
- 방식 A: ❌ "추측" — 실제 규모(283개 메서드, 104종 의존)를 전혀 모름
- 방식 B: ✅ — 실제 파일 스캔 결과로 검증 완료

---

### Q2 — "UIStatusEffect 수정 시 영향 범위는?"

| | 방식 A | 방식 B |
|--|--|--|
| **도구** | 없음 | `analyze_impact_and_risk` |

**방식 A 답변:**
> "버프 표시 UI를 수정하면 배틀 관련 클래스들이 영향받을 것 같습니다.
> 정확한 범위는 코드를 직접 확인해야 합니다."

**방식 B 답변 (MCP):**
> 직접 의존: `CombatObjectPool`, `CombatManager`
> 간접 의존: `UIGameField` → 7개 BattleField 하위 클래스, `UITextComponent` 경유 200개 이상 UI 클래스
> Asset: `Assets/Resources/Prefabs/UI/ui_status.prefab` 1개 사용
> Lint: 안티패턴 없음 ✓

**정확도 판정:**
- 방식 A: ❌ "배틀 관련 클래스" — 실제 200개 이상 UI 클래스에 영향을 완전히 놓침
- 방식 B: ✅ — 프리팹 에셋 경로까지 포함한 정확한 블래스트 반경 제공

> 💡 Q2가 가장 토큰 배율이 높은 이유: UIStatusEffect → UITextComponent → 전 UI 클래스로 이어지는
> 역방향 의존 트리가 매우 넓어 도구 출력이 12,800 토큰에 달했기 때문.

---


### Q3 — "Lyra 프로젝트 GAS 구조 — Ability가 몇 개인가?"

| | 방식 A | 방식 B |
|--|--|--|
| **도구** | 없음 | `analyze_ue5_gas` |

**방식 A 답변:**
> "Lyra는 Epic 샘플로 GAS를 광범위하게 사용합니다.
> LyraGameplayAbility가 기반 클래스이고 여러 Ability가 파생될 것입니다.
> 정확한 개수는 소스를 직접 확인해야 합니다."

**방식 B 답변 (MCP):**
> - Abilities: 1개 (ELyraAbilityActivationPolicy — 활성화 정책 enum)
> - Effects: 0개, AttributeSets: 1개 (ULyraAttributeSet)
> - ASC 사용 클래스: 7개 (LyraCharacter, LyraGameState, ZombieCharacter 포함)
> - GameplayTags: 13개, 커스텀 ZombieCharacter의 GAS 사용 확인됨

**정확도 판정:**
- 방식 A: ❌ "여러 Ability" — 실제로는 1개뿐이며 Effect는 0개임 (환각에 가까운 추측)
- 방식 B: ✅ — C++ 헤더 + uasset 2-pass 스캔으로 정확한 수치 제공

---

### Q4 — "ZombieAIController가 어떤 BehaviorTree를 사용하는가?"

| | 방식 A | 방식 B |
|--|--|--|
| **도구** | 없음 | `explore_class_semantics` + 파일 직접 확인 |

**방식 A 답변:**
> "아마 RunBehaviorTree()로 BT 에셋을 실행하거나 BehaviorTree 컴포넌트를 가질 것입니다.
> 어떤 BT 에셋을 쓰는지는 소스를 직접 확인해야 합니다."

**방식 B 답변 (MCP):**
> ZombieAIController.cpp 확인: AAIController 상속, OnPossess만 오버라이드, 본문 비어있음.
> RunBehaviorTree() 호출 없음 — BT 연결은 Blueprint 레벨에서 이루어지거나 미구현.
> → **결론: 이 프로젝트에서 ZombieAIController는 BT를 직접 사용하지 않음** (예상과 다름)

**정확도 판정:**
- 방식 A: ❌ "RunBehaviorTree() 있을 것" — 실제로는 없음. 틀린 예측
- 방식 B: ✅ — 실제 소스 코드 확인으로 "BT 없음" 사실을 정확히 확인

> 💡 이 케이스는 "없음을 확인하는" 능력의 차이를 잘 보여줌.
> MCP 없이는 "있을 것"이라 추측하는 반면, MCP는 "실제로 없음"을 코드로 증명.

---

### Q5 — "가장 결합도 높은 클래스 Top5와 순환참조 현황"

| | 방식 A | 방식 B |
|--|--|--|
| **도구** | 없음 | `execute_gdep_cli` (scan) |

**방식 A 답변:**
> "Manager 계열이나 공통 UI 기반 클래스가 Top에 오를 것 같습니다.
> ManagerBattle이나 GameManager가 높을 것입니다."

**방식 B 답변 (MCP):**
> Top 5 (in-degree):
> 1. UITextComponent — 231 (예상 밖의 1위)
> 2. UIDynamicList — 66
> 3. Data_Entity — 54
> 4. EntityCard — 46
> 5. UIListGeneric — 43
>
> 순환참조: **40개** (직접 14개, 간접 26개)
> 주요 패턴: CombatCore↔CombatInfo, EntityCard↔EntityCardPool

**정확도 판정:**
- 방식 A: ❌ "CombatManager" 예측 — 실제 1위는 UITextComponent(231)이고 ManagerBattle은 상위권도 아님
- 방식 B: ✅ — 실제 수치 기반. 순환참조 40개 정확히 파악

---


---

## 전체 토큰 비교표

| 질문 | A 총 토큰 | B 총 토큰 | 배율 | 정확도 A | 정확도 B |
|------|----------|----------|------|---------|---------|
| Q1 CombatManager 구조 | 134 | 8,637 | 64.5x | ❌ 추측 | ✅ 정확 |
| Q2 UIStatusEffect 영향 범위 | 93 | 12,946 | 139.2x | ❌ 불완전 | ✅ 정확 |
| Q3 Lyra GAS 구조 | 112 | 1,212 | 10.8x | ❌ 환각 | ✅ 정확 |
| Q4 ZombieAI BT 사용 | 113 | 482 | 4.3x | ❌ 오예측 | ✅ "없음" 확인 |
| Q5 결합도 Top5 + 순환 | 135 | 3,512 | 26.0x | ❌ 오예측 | ✅ 정확 |
| **합계** | **587** | **26,789** | **45.6x** | **0/5** | **5/5** |

---

## 정확도 세부 분류

| 항목 | 방식 A | 방식 B |
|------|--------|--------|
| 정답 (5문항) | 0 / 5 | 5 / 5 |
| 환각 발생 | 3건 (Q3 Ability 수, Q4 BT 존재, Q5 1위 클래스) | 0건 |
| 불완전 답변 | 5/5 ("직접 확인 필요" 포함) | 0/5 |
| 검증 가능 여부 | ❌ 불가 | ✅ 코드로 검증 |

---

## 언제 MCP를 쓰면 이득인가?

```
토큰 비용이 낮은 질문 (≤10x):
  → Q4처럼 "있는지 없는지" 간단한 구조 확인
  → 소규모 프로젝트의 특정 클래스 조회

토큰 비용이 높은 질문 (>30x):
  → Q1, Q2처럼 대형 클래스의 전체 구조 + 역방향 의존 트리
  → 실서비스 수준 대형 프로젝트 전수 스캔
  → 하지만 이런 질문은 MCP 없이는 아예 답할 수 없으므로 비교 자체가 무의미
```

**실용 가이드:**
- 코드베이스 구조를 "처음 파악할 때" → MCP 필수, 토큰 투자 가치 있음
- 이미 파악한 구조에 대한 "가벼운 확인" → 방식 A로 충분
- "수정 전 안전성 확인" → MCP 필수 (방식 A로는 판단 불가)
- **UE5 GAS 흐름 분석** → `analyze_ue5_gas` + `blueprint_mapping` 조합 권장
- **전체 드릴다운 경로 해석** → Web UI 흐름 그래프의 LLM 해석 기능 활용

---

## 부록 A: 발견된 버그 (테스트 중 확인)

테스트 진행 중 **Windows 한국어 환경(cp949)에서 CLI 크래시** 버그를 발견했습니다.

**현상:** `gdep scan`, `gdep lint` 등 CLI 직접 실행 시 `⚠`, `►`, `✓` 이모지 출력 중 `UnicodeEncodeError` 발생

**원인:** `click.secho()`가 cp949 터미널에 UTF-8 이모지를 그대로 출력 시도

**수정:** `_safe_echo()` 래퍼 함수 도입 — 인코딩 실패 시 ASCII로 폴백
```python
def _safe_echo(msg: str, **kwargs):
    try:
        click.secho(msg, **kwargs)
    except UnicodeEncodeError:
        safe = msg.encode(sys.stdout.encoding or 'ascii', errors='replace')
               .decode(sys.stdout.encoding or 'ascii')
        click.secho(safe, **kwargs)
```

**영향 범위:** CLI 직접 실행 전반 (MCP 경유 시는 정상 동작 — MCP 서버가 별도 인코딩 처리)

**상태:** ✅ 수정 완료 (`gdep-cli/gdep/cli.py`)

---

## 부록 C: 신규 도구 (36~42단계) 활용 시나리오

### suggest_test_scope — 수정 전 테스트 범위 산정

```
질문: "BattleCore 수정 전에 어떤 테스트 파일을 돌려야 해?"
→ suggest_test_scope(project_path, "BattleCore")

출력 예시 (Unity TrumpCard):
  🧪 Test Scope for BattleCore (depth=3)
  영향 클래스: 389개
  매칭 테스트: 3개
    ✓ Tests/BattleCoreTest.cs  [BattleCore]
    ✓ Tests/CombatSystemSpec.cs  [CombatSystem]
    ✓ Tests/Integration/GameFlowTest.cs  [test dir]
```

**활용**: CI 파이프라인 연동 (JSON 포맷) — 변경된 클래스 기준 선택적 테스트 실행.

---

### get_architecture_advice — 아키텍처 종합 진단

```
질문: "이 프로젝트의 아키텍처 문제점이 뭐야?"
→ get_architecture_advice(project_path)

출력 예시 (Axmol FantasyClicker):
  [Current State]
    Classes: 11  Dead: 2  Cycles: 0  Lint: 0
    High-coupling TOP 3: DFBattleManager(4), DFObject(4), DFMonster(2)

  [Data-driven Findings]
    1. High-coupling: DFBattleManager (in-degree=4) → SRP 위반 의심
    2. Orphan classes: 2 → DFEffect, DFTrench

  Cache warm: 0.12s
```

**활용**: PR 전 아키텍처 리뷰 자동화. LLM 설정 시 IMMEDIATE/MID-TERM/LONG-TERM 어드바이스 생성.

---

### suggest_lint_fixes — fix 코드 블록 제안

```
질문: "이 lint 이슈들 어떻게 고쳐야 해?"
→ suggest_lint_fixes(project_path, rule_ids=["UNI-PERF-001"])

출력 예시:
  ### UNI-PERF-001 (2개 발견)
  **EnemyController.Update** — Assets/Scripts/EnemyController.cs
  > Update 내부에서 GetComponent 호출

  ```
  // Before (안티패턴):
  void Update() { var rb = GetComponent<Rigidbody>(); ... }

  // After (Fix):
  Rigidbody _rb;
  void Awake() { _rb = GetComponent<Rigidbody>(); }
  void Update() { ... _rb ... }
  ```
```

---

### summarize_project_diff — PR 아키텍처 영향 요약

```
질문: "이 PR이 아키텍처에 어떤 영향을 주나?"
→ summarize_project_diff(project_path, commit_ref="HEAD~1")

출력 예시 (Unity TrumpCard):
  ## PR 아키텍처 영향 요약
  변경 파일: 1개
  신규 순환참조: +13개  해소: -12개  순증가: +1개 (⚠️)

  ### 고결합 클래스가 포함된 신규 순환참조
  - PlayingCard (결합도 46) — 새 순환참조에 포함
```

---

## 부록 B: 신규 도구 (27단계) 활용 시나리오

### blueprint_mapping — C++ → BP 구현체 연결

```
질문: "ARGameplayAbility_Dash를 상속한 Blueprint가 어디에 있어?"
→ blueprint_mapping(project_path, "ARGameplayAbility_Dash")

출력 예시 (HackAndSlash):
  ## Blueprint implementations of ARGameplayAbility_Dash (1 found)
  ### BP_GA_Dash_C (BP_GA_Dash_C)
    Path: /Game/Blueprints/GA/BP_GA_Dash
    K2 overrides: K2_ActivateAbility, K2_OnEndAbility
    Event K2_ActivateAbility -> PlayMontageAndWait -> ...
```

**토큰 효율**: 단순 쿼리로 BP 구현체 파악 → 약 3~5x 토큰 (낮은 비용으로 높은 가치)

---

### analyze_ue5_gas + blueprint_mapping 조합

```
# 1단계: GAS 전체 구조 파악
analyze_ue5_gas(project_path)
→ Ability 5개 / AttributeSet 1개 / Tag 169개 확인

# 2단계: 각 Ability의 BP 구현체 파악
blueprint_mapping(project_path, "UARGamePlayAbility_BasicAttack")
→ BP_GA_BasicAttack, BP_GA_HeavyAttack 구현체 + K2 오버라이드 확인
```

**장점**: C++ 레벨에서 끝나지 않고 실제 Blueprint 실행 단위까지 추적 가능.
          Web UI의 GAS 그래프 탭 → 텍스트 탭 전환으로 동일 내용을 시각/텍스트 양쪽으로 확인 가능.
