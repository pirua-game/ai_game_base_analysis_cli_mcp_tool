# gdep Web UI

[gdep](../../README_KR.md)의 브라우저 기반 인터페이스 — 게임 코드베이스(Unity · UE5 · Axmol · C++)를 위한 인터랙티브 시각화 및 AI 기반 분석 도구입니다.

---

## 개요

gdep Web UI는 gdep CLI를 로컬 웹 앱으로 감싸, 터미널 출력 대신 다음을 제공합니다:

- 인터랙티브 의존성 그래프 및 호출 흐름 다이어그램
- 저장할 때마다 자동으로 분석하는 실시간 파일 감시 패널
- 실제 코드베이스에 대해 툴 호출이 가능한 AI 채팅 에이전트
- 엔진 전용 탐색기 (UE5 GAS, Blueprint 매핑, Animator, BehaviorTree …)

**스택:** React 19 + TypeScript + Vite + TailwindCSS (프론트엔드) · FastAPI + Python (백엔드)

---

## 빠른 시작

### 원클릭 (권장)

**1단계 — 설치** (프로젝트 루트에서 최초 1회 실행)

```
# Windows
install.bat

# macOS / Linux
chmod +x install.sh && ./install.sh
```

**2단계 — 실행**

```
# Windows — 백엔드 + 프론트엔드를 별도 터미널에서 자동 실행
run.bat

# macOS / Linux — 별도 터미널 두 개에서 실행
./run.sh          # 터미널 1: 백엔드  (포트 8000)
./run_front.sh    # 터미널 2: 프론트엔드 (포트 5173)
```

브라우저에서 `http://localhost:5173`을 열고 사이드바에 프로젝트 소스 폴더 경로를 입력하세요.

| URL | 서비스 |
|-----|--------|
| `http://localhost:5173` | 프론트엔드 (Web UI) |
| `http://localhost:8000` | 백엔드 API |

> **참고:** 비상업용 개발 도구입니다.
> UI 언어: **영어 및 한국어** 지원.
> 로컬 LLM: **Ollama** 지원 — `ollama serve` 실행 후 사이드바 LLM 설정에서 선택하세요.

---

### 수동 설치 (개발 환경)

```bash
# 1. 백엔드 의존성 설치
cd backend
pip install -r requirements.txt

# 2. 백엔드 시작 (포트 8000)
uvicorn main:app --reload

# 3. 두 번째 터미널 — 프론트엔드 설치 및 실행 (포트 5173)
cd ../frontend
npm install
npm run dev
```

---

## 기능

### 1. 클래스 브라우저

IDE 없이 프로젝트의 모든 클래스를 탐색합니다.

- 클래스별 필드, 메서드, 기반 클래스
- **상속 체인 breadcrumb** — 클릭 가능한 `A → B → C → D` 체인으로 상위 클래스로 바로 이동
- **Method Logic 패널** — 메서드 버튼 클릭 시 내부 제어 흐름(Guard / Branch / Loop / Switch / Always)을 5~10줄로 요약 표시. 소스 파일을 열지 않아도 메서드가 어떤 조건에서 어떻게 동작하는지 파악 가능
- 결합도 지표 및 Dead Code 플래그
- Unity Prefab / UE5 Blueprint 역참조
- 영향 분석 — 이 클래스를 변경하면 무엇이 깨지는지
- 테스트 범위 제안 — 실행해야 할 테스트 파일
- 수정 제안이 포함된 Lint 이슈 인라인 표시
- UE5 Blueprint↔C++ 매핑 상세 정보

#### Method Logic 상세

| 항목 | 설명 |
|------|------|
| **Guard** | `if (조건) return/throw` 형태의 조기 탈출 가드 |
| **Branch** | `if/else` 분기와 각 브랜치의 주요 호출 |
| **Loop** | `for/foreach/while` 반복문과 내부 핵심 호출 |
| **Switch** | `switch` 문 |
| **Exception** | `try/catch` 블록 |
| **Always** | 조건 없이 항상 실행되는 최상위 호출 |

> **Flow Graph와의 차이:** Flow Graph는 호출 체인 `A→B→C`를 보여주고,
> Method Logic은 메서드 *내부*의 조건·분기·반복 로직을 보여줍니다.

### 2. 흐름 그래프

메서드 호출 체인을 인터랙티브 노드 그래프로 시각화합니다.

- 임의 진입점에서 시작하는 실행 경로 애니메이션
- 색상 코드 노드: 진입점 · 비동기 · 디스패치 · 블루프린트 · 리프
- 모든 노드를 드릴다운하여 호출 트리 확장
- LLM 설명 패널 — "이 흐름이 무엇을 하는가?" 질문 가능
- C++→Blueprint 경계 교차 지원 (UE5)

### 3. 의존성 뷰

프로젝트 전체 아키텍처 헬스 대시보드.

- 순환 참조 감지 및 사이클 경로 하이라이트
- 높은 결합도 클래스 순위
- Dead Code 목록
- 상속 계층 그래프
- 프로젝트 전반 Prefab / Blueprint 사용 추적
- 임의 클래스에 대한 원클릭 영향 분석 및 테스트 범위

### 4. Watch 패널

코딩하는 동안 터미널 없이 실시간 피드백.

- 로컬 파일 감시자에 대한 WebSocket 연결
- 저장할 때마다: 영향 클래스 수 · 영향받는 테스트 파일 · Lint 경고
- 심각도 표시기(ok / warning / error)가 있는 접을 수 있는 결과 카드
- 설정 가능한 디바운스 및 분석 깊이
- 노이즈 감소를 위한 대상 클래스 필터

### 5. AI 에이전트 채팅

실제 코드를 읽는 대화형 AI.

- 실시간 응답을 위한 Server-Sent Events 스트리밍
- 툴 호출 실행 단계 인라인 표시
- 프리셋 쿼리: 온보딩 · 순환 참조 · God Object · GAS 분석 · 애니메이션 · AI 행동
- LLM 제공자 선택: Ollama · OpenAI · Claude · Gemini
- 세션 기반 대화 기록 및 초기화

---

## 엔진별 탐색기

| 엔진 | 기능 | 제공 정보 |
|------|------|---------|
| Unity | **UnityEvent 바인딩** | 코드 검색으로는 보이지 않는 인스펙터 와이어드 퍼시스턴트 호출 |
| Unity | **Animator 분석** | AnimatorController의 상태, 전환, 블렌드 트리 |
| UE5 | **GAS 탐색기** | Abilities, Effects, Attributes, Tags, ASC 소유자 — `detail_level`, `category`(태그 접두사), `query`(키워드) 필터 지원 |
| UE5 | **Blueprint 매핑** | C++ 클래스 → BP 구현체, K2 오버라이드, 이벤트, 변수 |
| UE5 | **Animation 분석** | ABP 상태, Montage 슬롯, GAS Notify |
| UE5 | **BehaviorTree** | 태스크/데코레이터/서비스 노드가 있는 BT 에셋 구조 |
| UE5 | **StateTree** | StateTree (UE 5.2+) 상태 + 전환 맵 |
| Axmol | **이벤트 바인딩** | EventDispatcher 및 스케줄러 바인딩 맵 |

모든 엔진 분석 결과에는 **신뢰도 뱃지**(🟢 HIGH / 🟡 MEDIUM / 🔴 LOW)가 표시됩니다.
데이터 소스(소스 코드 직접 분석 vs. 바이너리 `.uasset` 패턴 매칭)에 따라 신뢰도가 달라집니다.

### UE5 GAS 필터 옵션 (신규)

| 파라미터 | 설명 | 예시 |
|----------|------|------|
| `detail_level` | `summary`(기본) 또는 `full` 상세 보기 | — |
| `category` | 태그 접두사 필터 | `Event`, `Ability`, `Status` |
| `query` | 클래스명·태그명·에셋명 키워드 검색 | `Dash`, `Jump`, `Attack` |

---

## 설정 (사이드바)

| 설정 | 설명 |
|------|------|
| **Scripts 경로** | 프로젝트 소스 폴더의 절대 경로 |
| **Context 버튼** | 프로젝트 AI 컨텍스트(AGENTS.md) 보기 및 `gdep init` 실행 |
| **엔진 프로파일** | 자동 · Unity · UE5 · Axmol · .NET · C++ |
| **분석 깊이** | 흐름 및 영향 추적에 대한 1~8 레벨 |
| **Focus 클래스** | 결과를 좁히기 위한 쉼표로 구분된 목록 |
| **LLM 제공자** | Ollama / OpenAI / Claude / Gemini + 모델 + API 키 |
| **테마** | 다크 / 라이트 |
| **언어** | 영어 / 한국어 |

### 프로젝트 컨텍스트 (AGENTS.md)

캐시 새로고침 버튼 옆 **Context** 버튼을 클릭하면:

1. 자동 생성된 프로젝트 컨텍스트(또는 AGENTS.md가 있는 경우 그 내용) 확인
2. **Init AGENTS.md** 클릭 → `.gdep/AGENTS.md` 생성 (Claude Code, Cursor 등 AI 도구가 읽는 구조화된 프로젝트 개요)
3. 프로젝트가 변경된 경우 **Regen AGENTS.md**로 재생성

---

## API 레퍼런스

백엔드는 프론트엔드가 사용하는 REST + WebSocket API를 노출합니다. 모든 라우트는 `/api` 접두사가 붙습니다.

| 라우터 | 경로 | 목적 |
|--------|------|------|
| project | `POST /project/scan` | 결합도, 순환 참조, Dead Code |
| project | `POST /project/impact` | 클래스 블라스트 반경 |
| project | `POST /project/describe` | 상속 체인 포함 클래스 구조 |
| project | `POST /project/lint` | Lint 이슈 스캔 |
| project | `POST /project/advise` | LLM 아키텍처 조언 |
| project | `POST /project/test-scope` | 변경된 클래스의 테스트 파일 |
| project | `POST /project/diff-summary` | Git diff 아키텍처 영향 분석 |
| project | `POST /project/explain-method-logic` | 메서드 내부 제어 흐름 (Guard/Branch/Loop) |
| project | `GET  /project/context` | 프로젝트 AI 컨텍스트 / AGENTS.md 내용 |
| project | `POST /project/init` | `.gdep/AGENTS.md` 생성 |
| classes | `GET /classes/list` | 필드 + 메서드가 포함된 모든 클래스 |
| flow | `POST /flow/analyze` | 메서드 호출 그래프 |
| engine | `POST /engine/unity/events` | UnityEvent 바인딩 |
| engine | `POST /engine/unity/animator` | Animator 구조 |
| engine | `POST /engine/ue5/gas` | GAS 분석 (detail_level / category / query) |
| engine | `POST /engine/ue5/gas/graph` | GAS ReactFlow 그래프 |
| engine | `POST /engine/ue5/animation` | ABP + Montage 분석 |
| engine | `POST /engine/ue5/behavior_tree` | BehaviorTree 구조 |
| engine | `POST /engine/ue5/state_tree` | StateTree 구조 |
| engine | `POST /engine/axmol/events` | Axmol 이벤트 바인딩 |
| unity | `GET /unity/refs` | 모든 Prefab/Scene 참조 |
| ue5 | `GET /ue5/blueprint_refs` | 모든 Blueprint 참조 |
| ue5 | `GET /ue5/blueprint_mapping` | C++↔BP 상세 매핑 |
| agent | `POST /agent/run` | SSE 스트리밍 AI 에이전트 |
| agent | `POST /agent/reset` | 에이전트 세션 초기화 |
| llm | `POST /llm/analyze` | LLM 흐름 설명 |
| llm | `GET /llm/ollama/models` | 로컬 Ollama 모델 조회 |
| watch | `WS /watch` | 실시간 파일 변경 이벤트 |

---

## 디렉토리 구조

```
web/
├── backend/
│   ├── main.py                  # FastAPI 앱, CORS, 라우터 등록
│   ├── requirements.txt
│   └── routers/
│       ├── project.py           # scan / impact / describe / lint / advise / diff
│       │                        # explain-method-logic / context / init
│       ├── classes.py           # 클래스 목록 파서 (C# / C++ / UE5)
│       ├── flow.py              # 호출 그래프 추적기
│       ├── engine.py            # 엔진별 분석기 (GAS 필터 포함)
│       ├── unity.py             # Unity 참조 쿼리
│       ├── ue5.py               # UE5 Blueprint 쿼리
│       ├── agent.py             # SSE 에이전트 (툴 호출)
│       ├── llm.py               # LLM 제공자 브릿지
│       └── watch.py             # WebSocket 파일 감시자
└── frontend/
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── App.tsx              # 탭 레이아웃
        ├── store.tsx            # 전역 상태 + 캐싱
        ├── api/
        │   └── client.ts        # 타입이 지정된 API 함수
        ├── components/
        │   ├── Sidebar.tsx      # 프로젝트 설정 패널 + Context 모달
        │   ├── ClassBrowser.tsx # 클래스 탐색기 + Method Logic + 상속 체인
        │   ├── DependencyView.tsx  # 의존성 탭 + GAS 필터
        │   ├── WatchPanel.tsx   # 실시간 파일 감시자
        │   └── ConfidenceBadge.tsx  # HIGH/MEDIUM/LOW 신뢰도 pill 뱃지
        └── tabs/
            └── AgentChat.tsx
```

---

*[gdep](../../README_KR.md) 프로젝트의 일부 — 게임 코드베이스 분석 도구*
