# gdep-mcp — 게임 코드베이스 분석 MCP 서버

Claude Desktop, Cursor 등 AI 에이전트에서 [gdep](https://github.com/pirua-game/gdep)을 사용해
게임 프로젝트(Unity, UE5, C++, C#)를 분석할 수 있게 해주는 MCP 서버입니다.

**다른 언어로 읽기:**
[English](./README.md) · [日本語](./README_JA.md) · [简体中文](./README_ZH.md) · [繁體中文](./README_ZH_TW.md)

---

## ⚡ 빠른 설치

### npm 으로 설치 (권장 — git clone 불필요)

```bash
npm install -g gdep-mcp
```

`gdep`와 `mcp[cli]` Python 패키지를 자동으로 함께 설치합니다.

AI 에이전트 설정에 추가:

```json
{
  "mcpServers": {
    "gdep": {
      "command": "gdep-mcp"
    }
  }
}
```

> 각 도구 호출 시 `project_path`를 파라미터로 전달합니다. 설정에 프로젝트 경로 불필요.

### pip 으로 수동 설치

```bash
pip install gdep "mcp[cli]"
```

**Claude Desktop 설정** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "gdep": {
      "command": "/path/to/gdep-cli/.venv/bin/python",
      "args": ["/path/to/gdep-cli/gdep-mcp/server.py"],
      "cwd": "/path/to/gdep-cli"
    }
  }
}
```

---

## 🛠 도구 목록 (13개)

### 컨텍스트 도구 — 세션 시작 시 첫 호출 권장

| 도구 | 설명 |
|------|------|
| `get_project_context` | 프로젝트 전체 개요. `.gdep/AGENTS.md` 있으면 읽고, 없으면 즉석 생성 |

### High-level 의도 기반 도구 (4개)

| 도구 | 설명 |
|------|------|
| `analyze_impact_and_risk` | 클래스 수정 전 파급 범위 + 린트 |
| `trace_gameplay_flow` | 메서드 호출 체인 추적 + 소스 코드 |
| `inspect_architectural_health` | 결합도/순환참조/데드코드/안티패턴 |
| `explore_class_semantics` | 클래스 구조 + AI 3줄 요약 |

### Raw CLI 접근 (1개)

| 도구 | 설명 |
|------|------|
| `execute_gdep_cli` | `args: list[str]` — gdep CLI 전체 기능 직접 실행 |

### Unity 전용 (2개)

| 도구 | 설명 |
|------|------|
| `find_unity_event_bindings` | .prefab/.unity/.asset Inspector 바인딩 메서드 검출 |
| `analyze_unity_animator` | .controller → Layer/State/BlendTree 구조 |

### UE5 전용 (5개)

| 도구 | 설명 |
|------|------|
| `analyze_ue5_gas` | GA/GE/AS 클래스 + GameplayTag + ASC 사용처 |
| `analyze_ue5_behavior_tree` | BT_* .uasset → Task/Decorator/Service/Blackboard |
| `analyze_ue5_state_tree` | ST_* .uasset → Task/AIController 연결 |
| `analyze_ue5_animation` | ABP 상태머신 + Montage 섹션/슬롯/GAS Notify |
| `analyze_ue5_blueprint_mapping` | C++ 클래스 → BP 구현체 매핑 (K2 오버라이드/변수/GAS 태그) |

---

## 🔗 링크

- [메인 저장소](https://github.com/pirua-game/gdep)
- [전체 CLI 문서](https://github.com/pirua-game/gdep/blob/main/README.md)
- [성능 벤치마크](https://github.com/pirua-game/gdep/blob/main/docs/BENCHMARK.md)
