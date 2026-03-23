# gdep — 아키텍처 의사결정 및 개발 로드맵

> 이 문서는 프로젝트 아키텍처 방향성과 의사결정 기록을 보존합니다.
> 단계별 구현 현황은 HANDOVER.md, CLI 코어 목표는 DEVROADMAP.md 참고.

---

## 1. 프로젝트 포지셔닝

**AS-IS**: 인간 개발자가 터미널에서 사용하는 빠르고 강력한 게임 코드 분석 CLI 도구.

**TO-BE**: LLM 에이전트가 게임 코드를 시맨틱(Semantic)하게 이해할 수 있도록 데이터를 제공하는
**게임 엔진 전용 뇌(Brain)**이자 Stateless MCP 서버.

**핵심 경쟁력**: 단순한 코드 분석을 넘어, 코드와 게임 엔진 에셋(Unity Prefab, UE5 Blueprint)의
연결고리를 파악하는 하이브리드 분석 능력.

---

## 2. 핵심 아키텍처 의사결정

### 2.1. 인프라 구조: Stateless On-Demand ✅ 채택

**기각된 안**: 백그라운드 File Watcher + SQLite 캐싱
- 방대한 파일 수로 인한 리소스 낭비
- 증분 업데이트 시 캐시 불일치 위험

**채택된 안**: 하드디스크(파일 시스템)를 Single Source of Truth로 취급.
- 요청 즉시 최신 코드 분석 → 정합성 100% 보장
- mtime MD5 지문 기반 디스크 캐시로 warm 성능 확보 (.gdep/cache/)

### 2.2. MCP 툴 설계: High-level (의도 기반) API ✅ 채택

**기각된 안**: scan/flow/impact 등 로우레벨 기능 그대로 LLM에 노출
- LLM이 직접 조합 → 환각(Hallucination) + 토큰 낭비

**채택된 안**: 질문 의도에 즉시 대답하는 목적 지향적 High-level API 제공
- 13개 도구로 완성 (상세 목록: HANDOVER.md 섹션 3)

### 2.3. 파서 전략: Tree-sitter 기반 ✅ 채택

**UE5**: ue5_ts_parser.py (O(n) _clean_macros, catastrophic backtracking 차단)
**일반 C++**: cpp_ts_parser.py (Tree-sitter, ImportError 시 정규식 fallback)
**C# Unity**: gdep.dll (Roslyn 기반 C# 파서, OS 독립)

### 2.4. IDE 플러그인 ❌ 취소

VS Code Extension / JetBrains Rider Plugin 모두 제작 안 하기로 결정.
MCP + AGENTS.md + .cursorrules 방식으로 AI 에이전트 연동에 집중.

---

## 3. 기각된 아이디어

| 제안 | 기각 이유 |
|------|----------|
| Graph DB (SQLite) 영구 저장 | Stateless 장점 훼손. mtime 캐시로 충분 |
| Query Engine (Intent 파서) | LLM이 이미 intent 파싱 담당 |
| Risk Score 수치화 | "위험도 0.82" 자의적 점수는 실무에서 신뢰받지 못함 |
| VS Code / Rider 플러그인 | 직접 제작 안 함. MCP + AGENTS.md로 대체 |
| Unity Scene→Component 파싱 | 필요성 확인 후 추가 결정 (현재 보류) |

---

## 4. MCP 4대 핵심 도구 (구현 완료)

### analyze_impact_and_risk
- **목적**: 특정 클래스 수정 전 사이드 이펙트 + 코드 결함 리포팅
- **내부**: impact(역방향 의존성 트리) + lint(안티패턴) 결합

### trace_gameplay_flow
- **목적**: 버그 원인 파악용 런타임 콜 스택 + 실제 코드 발췌
- **내부**: flow(호출 트리) + read_source(소스 코드) 결합
- **UE5 추가**: C++→BP K2_ 브릿지 (bpBridge 플래그)

### inspect_architectural_health
- **목적**: 데드 코드, 순환 참조, 전체 안티패턴 한 번에 검사
- **내부**: scan(circular+dead_code+include_refs+deep) + lint() 결합

### explore_class_semantics
- **목적**: 낯선 클래스 역할/인터페이스/AI 요약 즉시 파악
- **내부**: describe(summarize=True) + .gdep/cache/summaries/ 캐시

---

## 5. 완료 마일스톤

| 우선순위 | 항목 | 상태 |
|---------|------|------|
| 1순위 | CI/CD — `gdep diff --fail-on-cycles` GitHub Actions 템플릿 | ✅ 18단계 완료 |
| 2순위 | 원클릭 설치 (`install.bat` / `install.sh`) | ✅ 25단계 완료 |
| 3순위 | 게임 엔진 특화 Linter 고도화 (13개 규칙) | ✅ 28단계 완료 |
| 4순위 | mtime 기반 Incremental 캐시 | ✅ 20+30단계 완료 |
| 5순위 | Blueprint↔C++ 매핑 + GAS 발동 흐름 통합 | ✅ 22단계 완료 |
| 6순위 | 오픈소스 배포 (PyPI + npm + GitHub) | ✅ 30단계 완료 |
| 7순위 | 일반 C++ Tree-sitter 파서 확장 | ✅ 35단계 완료 |

## 6. 미완료 항목

| 항목 | 우선순위 | 비고 |
|------|---------|------|
| `.cursorrules` 자동 생성 | 🟡 중기 | gdep init --cursorrules 옵션 |
| `cpp_runner.flow()` 구현 | 🟡 중기 | 일반 C++ 호출 체인 추적 |
| Unity Scene→Component 파싱 | 🔵 보류 | 필요 시 추가 |
