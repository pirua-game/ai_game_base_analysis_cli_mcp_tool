# gdep Web UI

[gdep](../../README_KR.md)의 브라우저 기반 인터페이스 — Unity · UE5 · Axmol · C++ 게임 코드베이스를 인터랙티브하게 시각화하고 AI로 분석합니다.

---

## 개요

gdep Web UI는 gdep CLI를 로컬 웹 애플리케이션으로 감싸, 터미널 출력을 다음으로 대체합니다:

- 인터랙티브 의존성 그래프 및 호출 흐름 다이어그램
- 저장 시마다 자동 분석하는 실시간 파일 감시 패널
- 실제 코드베이스를 읽는 AI 채팅 에이전트 (툴 콜링 포함)
- 엔진 전용 탐색기 (UE5 GAS, Blueprint 매핑, Animator, BehaviorTree 등)

**스택:** React 19 + TypeScript + Vite + TailwindCSS (프론트엔드) · FastAPI + Python (백엔드)

---

## 빠른 시작

### 원클릭 실행 (권장)

**1단계 — 설치** (프로젝트 루트에서 최초 1회 실행)

```
# Windows
install.bat

# macOS / Linux
chmod +x install.sh && ./install.sh
```

**2단계 — 실행**

```
# Windows — 백엔드 + 프론트엔드를 각각 별도 터미널 2개로 자동 실행
run.bat

# macOS / Linux — 터미널을 각각 따로 열어 실행
./run.sh          # 터미널 1: 백엔드  (포트 8000)
./run_front.sh    # 터미널 2: 프론트엔드 (포트 5173)
```

브라우저에서 `http://localhost:5173` 을 열고 사이드바에서 프로젝트의 스크립트 폴더를 지정하세요.

| URL | 서비스 |
|-----|--------|
| `http://localhost:5173` | 프론트엔드 (Web UI) |
| `http://localhost:8000` | 백엔드 API |

> **참고:** 상용 프로그램이 아니며 현재도 개발 중입니다 — 일부 기능이 완벽하지 않을 수 있습니다.
> UI 지원 언어: **영어(English) 및 한국어** 2개 언어만 지원합니다.
> 로컬 LLM: **Ollama** 사용 가능 — `ollama serve` 실행 후 사이드바 LLM 설정에서 선택하세요.

---

### 수동 설치 (개발 모드)

```bash
# 1. 백엔드 의존성 설치
cd backend
pip install -r requirements.txt

# 2. 백엔드 실행 (포트 8000)
uvicorn main:app --reload

# 3. 두 번째 터미널 — 프론트엔드 설치 및 실행 (포트 5173)
cd ../frontend
npm install
npm run dev
```

---

## 기능

### 1. 클래스 브라우저 (Class Browser)

IDE 없이 프로젝트의 모든 클래스를 탐색합니다.

- 클래스별 필드, 메서드, 부모 클래스 목록
- 커플링 지표 및 데드 코드 표시
- Unity Prefab / UE5 Blueprint 역참조
- 영향 분석 — 이 클래스를 변경하면 무엇이 깨지는가
- 테스트 범위 제안 — 어떤 테스트 파일을 실행해야 하는가
- 인라인 린트 이슈 및 수정 제안
- UE5 Blueprint↔C++ 매핑 상세 정보

### 2. 플로우 그래프 (Flow Graph)

메서드 호출 체인을 인터랙티브 노드 그래프로 시각화합니다.

- 임의의 진입점에서 애니메이션으로 실행 경로 표시
- 색상으로 구분된 노드: 진입점 · 비동기 · 디스패치 · 블루프린트 · 리프
- 노드 클릭으로 하위 호출 트리 드릴다운
- LLM 설명 패널 — "이 흐름이 무엇을 하는가?" 질문 가능
- C++→Blueprint 경계 통과 시각화 지원 (UE5)

### 3. 의존성 뷰 (Dependency View)

전체 프로젝트의 아키텍처 건강도 대시보드입니다.

- 순환 의존성 감지 및 사이클 경로 하이라이트
- 높은 커플링 클래스 순위
- 데드 코드 목록
- 상속 계층 그래프
- 프로젝트 전체의 Prefab / Blueprint 사용 현황 추적
- 클릭 한 번으로 임의 클래스의 영향 분석 및 테스트 범위 확인

### 4. 워치 패널 (Watch Panel)

코딩 중 터미널 없이 즉각적인 피드백을 받습니다.

- 로컬 파일 감시기에 WebSocket으로 연결
- 저장할 때마다: 영향받는 클래스 수 · 테스트 파일 수 · 린트 경고
- 심각도 표시기가 있는 접을 수 있는 결과 카드 (ok / warning / error)
- 디바운스 시간 및 분석 깊이 설정 가능
- 노이즈 감소를 위한 대상 클래스 필터 옵션

### 5. 에이전트 채팅 (Agent Chat)

실제 코드를 읽는 대화형 AI입니다.

- Server-Sent Events 스트리밍으로 실시간 응답
- 툴 콜링 실행 단계 인라인 표시
- 사전 설정 쿼리: 온보딩 · 순환 참조 · God Object · GAS 분석 · 애니메이션 · AI 행동
- LLM 제공자 선택: Ollama · OpenAI · Claude · Gemini
- 세션 기반 대화 기록 및 초기화

---

## 엔진 전용 탐색기

| 엔진 | 기능 | 제공 내용 |
|------|------|-----------|
| Unity | **UnityEvent 바인딩** | 코드 검색에서 보이지 않는 Inspector 연결 퍼시스턴트 호출 |
| Unity | **Animator 분석** | AnimatorController의 상태, 전환, 블렌드 트리 |
| UE5 | **GAS 탐색기** | Ability, Effect, Attribute, Tag, ASC 오너 |
| UE5 | **Blueprint 매핑** | C++ 클래스 → BP 구현, K2 오버라이드, 이벤트, 변수 |
| UE5 | **Animation 분석** | ABP 상태, Montage 슬롯, GAS Notify |
| UE5 | **BehaviorTree** | Task/Decorator/Service 노드를 포함한 BT 에셋 구조 |
| UE5 | **StateTree** | StateTree(UE 5.2+) 상태 + 전환 맵 |
| Axmol | **이벤트 바인딩** | EventDispatcher 및 Scheduler 바인딩 맵 |

---

## 설정 (사이드바)

| 설정 | 설명 |
|------|------|
| **Scripts path** | 프로젝트 소스 폴더의 절대 경로 |
| **Engine profile** | auto · Unity · UE5 · Axmol · .NET · C++ |
| **Analysis depth** | 플로우 및 영향 분석 깊이 (1–8 레벨) |
| **Focus classes** | 결과를 좁히기 위한 쉼표로 구분된 클래스 목록 |
| **LLM provider** | Ollama / OpenAI / Claude / Gemini + 모델 + API 키 |
| **Theme** | 다크 / 라이트 |
| **Language** | English / 한국어 |

---

## API 레퍼런스

백엔드는 프론트엔드가 소비하는 REST + WebSocket API를 제공합니다. 모든 경로는 `/api` 접두사를 사용합니다.

| 라우터 | 경로 | 용도 |
|--------|------|------|
| project | `POST /project/scan` | 커플링, 순환 의존성, 데드 코드 |
| project | `POST /project/impact` | 클래스의 영향 범위 분석 |
| project | `POST /project/lint` | 린트 이슈 스캔 |
| project | `POST /project/advise` | LLM 아키텍처 조언 |
| project | `POST /project/test-scope` | 변경된 클래스에 대한 테스트 파일 |
| project | `POST /project/diff-summary` | git diff의 아키텍처 변화 요약 |
| classes | `GET /classes/list` | 필드 + 메서드를 포함한 전체 클래스 목록 |
| flow | `POST /flow/analyze` | 메서드 호출 그래프 |
| engine | `GET /engine/unity/events` | UnityEvent 바인딩 |
| engine | `GET /engine/unity/animator` | Animator 구조 |
| engine | `GET /engine/ue5/gas` | GAS 분석 |
| engine | `GET /engine/ue5/animation` | ABP + Montage 분석 |
| engine | `GET /engine/ue5/behavior_tree` | BehaviorTree 구조 |
| engine | `GET /engine/ue5/state_tree` | StateTree 구조 |
| engine | `GET /engine/axmol/events` | Axmol 이벤트 바인딩 |
| unity | `GET /unity/refs` | 전체 Prefab/Scene 참조 |
| ue5 | `GET /ue5/blueprint_refs` | 전체 Blueprint 참조 |
| ue5 | `GET /ue5/blueprint_mapping` | C++↔BP 상세 매핑 |
| agent | `POST /agent/run` | SSE 스트리밍 AI 에이전트 |
| agent | `POST /agent/reset` | 에이전트 세션 초기화 |
| llm | `POST /llm/analyze` | LLM 플로우 설명 |
| llm | `GET /llm/ollama/models` | 로컬 Ollama 모델 탐색 |
| watch | `WS /watch` | 실시간 파일 변경 이벤트 |

---

## 디렉터리 구조

```
web/
├── backend/
│   ├── main.py                  # FastAPI 앱, CORS, 라우터 등록
│   ├── requirements.txt
│   └── routers/
│       ├── project.py           # scan / impact / lint / advise / diff
│       ├── classes.py           # 클래스 목록 파서 (C# / C++ / UE5)
│       ├── flow.py              # 호출 그래프 추적기
│       ├── engine.py            # 엔진별 분석기
│       ├── unity.py             # Unity 참조 쿼리
│       ├── ue5.py               # UE5 Blueprint 쿼리
│       ├── agent.py             # SSE 에이전트 (툴 콜링)
│       ├── llm.py               # LLM 제공자 브릿지
│       └── watch.py             # WebSocket 파일 감시기
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── App.tsx              # 탭 레이아웃
        ├── store.tsx            # 전역 상태 + 캐싱
        ├── components/
        │   └── Sidebar.tsx      # 프로젝트 설정 패널
        └── tabs/
            ├── ClassBrowser.tsx
            ├── FlowGraph.tsx
            ├── DependencyView.tsx
            ├── WatchPanel.tsx
            └── AgentChat.tsx
```

---

*[gdep](../../README_KR.md) 프로젝트의 일부 — 게임 코드베이스 분석 도구*
