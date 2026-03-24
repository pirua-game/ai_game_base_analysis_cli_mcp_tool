# 🗺️ gdep Web UI — 사용 가이드

게임 코드베이스를 브라우저에서 시각적으로 분석하는 Web UI입니다.
Unity · Unreal Engine 5 · Cocos2d-x · .NET · C++ 프로젝트를 지원합니다.

> **CLI 사용법 → [README.md](./README.md)**
> **MCP 서버 설정 → [gdep-cli/gdep-mcp/README.md](./gdep-cli/gdep-mcp/README.md)**

---

## 📋 사전 요구사항

| 항목 | 버전 | 비고 |
|------|------|------|
| Python | 3.11 권장 | [python.org](https://www.python.org/downloads/) |
| Node.js | 18 이상 | [nodejs.org](https://nodejs.org/) |
| .NET SDK | 8.0 이상 | C# 분석 시 필요 |
| Ollama | 선택 | 로컬 LLM 사용 시 |

---

## 🚀 최초 설치 — 원클릭

**Windows**
```
F:\Develop\AI\gdep\install.bat  ← 더블클릭
```

**macOS / Linux**
```bash
chmod +x install.sh
./install.sh
```

Python 가상환경 생성, pip install, npm install을 자동으로 처리합니다.
완료 후 Claude Desktop MCP 설정 방법도 출력됩니다.

### 수동 설치

```bash
cd gdep-cli
py -3.11 -m venv .venv          # Windows
python3 -m venv .venv           # macOS/Linux
.venv/Scripts/pip install -e .  # Windows
.venv/bin/pip install -e .      # macOS/Linux
cd frontend && npm install
```

---

## ▶️ 실행

### 가장 간단한 방법

**Windows**
```
F:\Develop\AI\gdep\run.bat  ← 더블클릭
```

**macOS / Linux**
```bash
# 터미널 1 — 백엔드
./run.sh

# 터미널 2 — 프론트엔드 (새 탭/창에서)
./run_frontend.sh
```

백엔드(8000)와 프론트엔드(5173)를 터미널을 나눠 실행합니다.
각 터미널에서 `Ctrl+C`로 개별 종료합니다.

### 수동 실행

**터미널 1 — 백엔드 (포트 8000)**
```bash
cd gdep-cli/backend
# Windows
..\venv\Scripts\python.exe -m uvicorn main:app --port 8000
# macOS/Linux
../.venv/bin/python -m uvicorn main:app --port 8000
```

**터미널 2 — 프론트엔드 (포트 5173)**
```bash
cd gdep-cli/frontend
node_modules/.bin/vite        # macOS/Linux
node_modules\.bin\vite.cmd    # Windows
```

브라우저에서 `http://localhost:5173` 접속

---

## 🖥️ UI 구성

### 사이드바

| 항목 | 설명 |
|------|------|
| Scripts 경로 | 분석할 프로젝트의 Source 또는 Assets\Scripts 경로 입력 |
| 엔진 프로파일 | 자동 감지 또는 수동 선택 (Unity/Unreal/Cocos2d-x/.NET/C++) |
| 분석 깊이 | 흐름 분석 시 추적 단계 수 (기본 3) |
| Focus 클래스 | 흐름 분석에서 깊이 추적할 클래스 지정 |
| LLM 설정 | Ollama / OpenAI / Claude / Gemini 설정 |

경로 입력 후 Enter 또는 🔄 버튼 클릭 → 프로젝트 자동 감지 및 클래스 로딩

---

## 📂 클래스 브라우저 탭

프로젝트의 모든 클래스를 목록으로 표시합니다.

**클래스 분류 아이콘**
- 🟢 프로젝트 클래스 (직접 작성한 코드)
- 🟡 엔진 파생 클래스 (MonoBehaviour, AActor 등 상속)
- 🔴 엔진 기저 클래스 (엔진 자체 클래스)

**클래스 선택 시 상세 패널**
- 상속 관계, 필드, 메서드 목록
- Unity: 프리팹/씬 사용처 표시
- UE5: Blueprint 구현체 카드 표시 — K2 오버라이드, 변수, GameplayTag를 파일별 접기/펼치기 카드로 확인
- 라이프사이클 진입점 버튼 (BeginPlay, Awake, Start 등)
- 메서드 버튼 클릭 → 흐름 그래프로 자동 이동

**Lint 버튼**
전체 안티패턴 스캔 실행. 심각도별 배지(✕ Error / ⚠ Warning / ℹ Info)와 규칙 ID 색상으로 구분 표시.

---

## 🔀 흐름 그래프 탭

메서드 호출 체인을 **계층형 트리 구조(dagre 레이아웃)**로 시각화합니다.
진입점이 최상단 중앙에 배치되고, 하위 호출이 아래로 펼쳐집니다.

**사용법**
1. 클래스 브라우저에서 메서드 버튼 클릭 → 자동으로 이 탭으로 이동
2. 브레드크럼에서 이전 진입점으로 돌아가기 (캐시 복원, 재분석 없음)

**노드 색상**
- 🟢 진입점 (분석 시작 메서드)
- 🔵 async 메서드
- 🟠 dispatch (이벤트/델리게이트)
- ⬜ 잎 노드 (더 이상 추적 불가)
- 🔵 [BP] Blueprint 노드 (C++→BP 경계, 파란 테두리 + 점선 엣지)
- 🟡 선택된 노드

**드릴다운 + 스택 추적**
노드 클릭 → 황색 하이라이트 → **드릴다운 →** 버튼 클릭
→ 해당 메서드를 새 진입점으로 더 깊이 분석
→ 브레드크럼에 `A → B → C → D` 형태로 경로 자동 기록

**🔵 Blueprint Bridge**
UE5에서 C++ → Blueprint 경계를 넘는 경우 상단에 `🔵 Blueprint bridge` 배지 표시.
BP 노드는 파란색 테두리, C++→BP 엣지는 파란 점선으로 구분됩니다.

**LLM 흐름 해석**
우상단 버튼 클릭 → 현재 흐름을 LLM이 자연어로 설명.
드릴다운 후 호출 시 **A~D 전체 경로 컨텍스트**를 포함한 분석을 제공합니다.
(사이드바에서 LLM 설정 필요)


---

## 🕸️ 의존성 · 분석 탭

탭바는 **공통 탭 4개 + 엔진 드롭다운 1개** 구조입니다.
Unity 프로젝트는 `🎮 Unity ▾`, UE5 프로젝트는 `⚙️ UE5 ▾` 드롭다운에서 엔진 전용 탭을 선택합니다.

### 공통 탭 (모든 엔진)

**📊 결합도 순위**
- in-degree 순위: 다른 클래스가 이 클래스를 참조하는 횟수
- 🔴 10↑ 위험 / 🟡 5~9 주의 / 🟢 4↓ 양호
- 순환 참조 목록 (직접/간접 구분)

**🌳 상속 관계 탐색**
- 클래스 선택 → ReactFlow 상속 그래프
- 부모/자식 클릭으로 네비게이션

**💀 Dead Code**
- "Dead Code 분석" 버튼 클릭 시 실행
- in-degree 0 클래스 목록 (Unity: 프리팹 역참조 필터 적용)

**💥 영향 분석**
- 클래스 선택 → "영향 분석" 버튼
- 이 클래스를 수정하면 영향받는 클래스 역방향 트리 표시
- Depth 1~5 조절 가능

---

### Unity 전용 탭 (`🎮 Unity ▾`)

**📦 프리팹 역참조**
클래스별로 어떤 .prefab / .unity 씬에서 사용되는지 표시

**🎯 Unity Events**
- .prefab/.unity/.asset 파일에서 Inspector에 연결된 메서드 검출
- 메서드 이름 필터 입력 가능
- 코드 검색으로는 찾기 어려운 Inspector 바인딩을 시각화

**🎬 Animator**
- .controller 파일 파싱 → 레이어/상태/블렌드트리 구조 표시

---

### UE5 전용 탭 (`⚙️ UE5 ▾`)

**📋 블루프린트 역참조**
클래스별로 어떤 .uasset 블루프린트/맵에서 사용되는지 표시

**⚡ GAS**
두 가지 뷰 토글로 확인합니다.

- **🔗 그래프 뷰 (기본)**: Ability → GE → AttributeSet 연결 관계를 ReactFlow 그래프로 시각화
  - GA(초록) / GE(보라) / AS(파랑) / Tag(주황) 색상 구분
  - dagre 계층형 레이아웃 자동 배치
- **📄 텍스트 뷰**: GameplayAbility / Effect / AttributeSet / Tag 전체 분석 리포트

**🎭 Animation**
- 에셋 타입: 전체 / ABP / Montage 선택
- 디테일 레벨: 요약 / 전체
- ABP: 상태머신 State, Slot, GAS Notify 추출
- Montage: 섹션 이름, Slot, Notify, AnimSequence 참조

**🤖 BT / StateTree**
- BehaviorTree: BT_* 에셋 → Task/Decorator/Service 구조
- StateTree: ST_* 에셋 → Task, AIController 연결
- 두 모드 토글로 전환

**🔗 BP 매핑**
- C++ 클래스 이름 입력 → 해당 클래스의 Blueprint 구현체 목록
- 빈 채로 분석 → 전체 프로젝트 BP 카탈로그
- K2 오버라이드, BP 변수, GameplayTag, GAS 파라미터 표시

> **Git LFS 프로젝트** (`git lfs pull` 미실행 상태)에서는 파일명 기반 목록을 자동으로 제공합니다.

---

## 🤖 AI 에이전트 탭

LLM이 gdep 도구 16개를 직접 호출해서 코드베이스를 분석합니다.

**사용 가능한 도구 (16개)**
공통: `scan` `describe` `read_source` `flow` `impact` `lint` `graph` `diff`
Unity 전용: `find_prefab_refs` `unity_events`
UE5 전용: `find_blueprint_refs` `analyze_gas` `analyze_animation` `analyze_behavior_tree` `analyze_state_tree` `blueprint_mapping`

**프리셋 버튼 (빠른 시작)**
- 🗺️ 온보딩, 🔍 순환 참조, ⚡ God Object, 🧹 단일 책임
- ⚡ GAS 분석, 🎭 애니메이션, 🤖 AI 행동

---

## 🎮 지원 엔진

| 엔진 | 클래스 분석 | 흐름 | 역참조 | GAS | BT/ST | ABP | Events |
|------|------------|------|--------|-----|-------|-----|--------|
| Unity (C#) | ✅ | ✅ | ✅ Prefab/Scene | - | - | ✅ .controller | ✅ UnityEvent |
| Unreal Engine 5 | ✅ | ✅ C++→BP | ✅ Blueprint/Map | ✅ 그래프 | ✅ | ✅ ABP/Montage | - |
| Cocos2d-x (C++) | ✅ | ✅ | - | - | - | - | - |
| .NET (C#) | ✅ | ✅ | - | - | - | - | - |
| C++ (일반) | ✅ | ✅ | - | - | - | - | - |

---

## ⚙️ 문제 해결

**UI가 하얗게 뜨거나 검게 뜰 때**
```bash
# 브라우저 캐시 완전 삭제 후 재접속
# Chrome: Ctrl+Shift+R (강제 새로고침)
```

**백엔드 연결 실패 시**
```
http://localhost:8000
# 응답: {"status": "ok", "message": "gdep API running"}
```

**클래스 목록이 비어 있을 때**
- 경로가 정확한지 확인 (Source 또는 Assets\Scripts 폴더)
- UE5: `Source\ProjectName` 폴더 경로 (프로젝트 루트 아님)
- 사이드바 "캐시 새로고침" 버튼 클릭

**GAS 그래프가 연결선 없이 나열될 때**
- GE 클래스가 C++ 대신 Blueprint로만 존재하는 경우 정상입니다
- GA의 `TSubclassOf<UGameplayEffect>` UPROPERTY를 통해 자동 연결 시도합니다
