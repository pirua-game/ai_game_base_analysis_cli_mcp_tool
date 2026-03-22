# gdep CI/CD 통합 가이드

> 여러분의 Unity / UE5 프로젝트 GitHub 레포에 gdep를 붙이는 방법입니다.
> 복붙해서 바로 쓸 수 있도록 작성했습니다.

---

## 개념 한 줄 요약

| 용어 | 의미 |
|------|------|
| **CI** | PR 올릴 때 자동으로 "이 코드 괜찮아?" 검사 |
| **CD** | 버전 태그를 달면 자동으로 배포 |
| **게이트** | 검사 실패 시 PR 머지를 막는 장치 |

---

## 시나리오 1 — Unity 프로젝트 PR 게이트

PR을 올릴 때마다 gdep가 **새 순환참조** 발생 여부를 검사합니다.
순환참조가 생기면 PR 머지 버튼이 빨간불로 바뀝니다.

```yaml
# .github/workflows/gdep-gate.yml  (여러분의 Unity 레포에 추가)
name: gdep Quality Gate

on:
  pull_request:
    branches: [ main, master, develop ]
    paths:
      - 'Assets/Scripts/**'   # Scripts 폴더 변경 시에만 실행

jobs:
  gdep-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - uses: actions/setup-dotnet@v4
        with:
          dotnet-version: '8.0.x'

      - name: Install gdep
        run: pip install gdep
        # 로컬 개발 환경: install.sh (macOS/Linux) 또는 install.bat (Windows)
        run: |
          gdep diff Assets/Scripts --commit HEAD~1 --fail-on-cycles
```


---

## 시나리오 2 — UE5 프로젝트 + 린트 리포트

PR마다 안티패턴(Tick 내 SpawnActor, Super:: 누락 등)을 검사하고
결과를 **JSON 아티팩트**로 저장합니다. 나중에 Actions 탭에서 다운로드 가능.

```yaml
# .github/workflows/gdep-gate.yml  (UE5 버전)
name: gdep Quality Gate

on:
  pull_request:
    branches: [ main ]
    paths:
      - 'Source/**'

jobs:
  gdep-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install gdep
        run: pip install gdep

      - name: Lint — anti-pattern scan
        run: |
          gdep lint Source/MyGame --format json > lint-report.json
          # 결과 요약 출력 (CI 로그에서 바로 확인)
          python3 -c "
          import json, sys
          d = json.load(open('lint-report.json'))
          errors = [x for x in d if x.get('severity') == 'Error']
          warnings = [x for x in d if x.get('severity') == 'Warning']
          print(f'Issues: {len(d)} total, {len(errors)} errors, {len(warnings)} warnings')
          # 탐지 규칙: UE5-GAS-001(CommitAbility 누락), UE5-BASE-001(Super 누락),
          #            UE5-GAS-002(비용 큰 쿼리), UE5-NET-001(ReplicatedUsing 누락) 등
          if errors:
              for e in errors: print(f'  ERROR [{e[\"rule_id\"]}]: {e[\"class_name\"]} — {e[\"message\"]}')
              sys.exit(1)
          "

      - name: Upload lint report
        if: always()   # 실패해도 아티팩트 저장
        uses: actions/upload-artifact@v4
        with:
          name: gdep-lint-report
          path: lint-report.json
```


---

## 시나리오 3 — gdep 자체 릴리즈 (버전 태그 → PyPI 자동 배포)

gdep 레포에서 버전을 올릴 때 사용합니다.

```bash
# 1. pyproject.toml의 version은 CI에서 자동으로 태그 버전으로 덮어씁니다.
#    수동으로 수정할 필요 없습니다.

# 2. 태그만 push하면 release.yml이 알아서 처리합니다.
git tag v0.2.0
git push origin v0.2.0

# 자동으로 일어나는 일:
#   1. gdep.dll 빌드
#   2. Frontend 빌드
#   3. PyPI에 패키지 업로드
#   4. GitHub Release 생성 + dll zip 첨부
```

### PyPI 토큰 등록 방법

1. https://pypi.org 에서 API 토큰 발급
2. GitHub 레포 → Settings → Secrets and variables → Actions
3. `PYPI_API_TOKEN` 이름으로 등록
4. `release.yml`의 주석 처리된 `password:` 줄 활성화

> **OIDC Trusted Publishing** 방식을 사용하면 토큰 없이도 배포 가능합니다.
> PyPI 프로젝트 설정에서 GitHub 레포를 신뢰 소스로 등록하면 됩니다.

---

## CI 뱃지 (README에 추가)

```markdown
[![CI](https://github.com/your-org/gdep/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/gdep/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/gdep)](https://pypi.org/project/gdep/)
```

---

## 탐지 가능한 Lint 규칙 (13개)

| Rule ID | 엔진 | 설명 | 심각도 |
|---------|------|------|--------|
| `UNI-PERF-001` | Unity | Update 내 GetComponent/Find 호출 | Error |
| `UNI-PERF-002` | Unity | Update 내 new/Instantiate 할당 | Error |
| `UNI-ASYNC-001` | Unity | Coroutine while(true) 내 yield 없음 | Error |
| `UNI-ASYNC-002` | Unity | Coroutine 내 FindObjectOfType/Resources.Load | Warning |
| `UE5-PERF-001` | UE5 | Tick 내 SpawnActor/LoadObject | Error |
| `UE5-PERF-002` | UE5 | BeginPlay 내 동기 LoadObject | Warning |
| `UE5-BASE-001` | UE5 | Super:: 호출 누락 | Warning |
| `UE5-GAS-001` | UE5 | ActivateAbility()에서 CommitAbility() 누락 | Error |
| `UE5-GAS-002` | UE5 | GAS Ability 내 비용 큰 world query | Warning |
| `UE5-GAS-003` | UE5 | BlueprintCallable 10개 초과 | Info |
| `UE5-GAS-004` | UE5 | BlueprintPure에 const 누락 | Info |
| `UE5-NET-001` | UE5 | Replicated에 ReplicatedUsing 콜백 없음 | Info |
| `GEN-ARCH-001` | 공통 | 순환 참조 | Warning |

---

## 흐름 요약

```
PR 올림
  └─ ci.yml 실행
       ├─ build-dll        C# dll 빌드
       ├─ lint-python      Python 코드 품질
       ├─ build-frontend   TypeScript 빌드
       ├─ test-linux       스모크 테스트
       ├─ test-windows     스모크 테스트
       └─ gate-cycles      새 순환참조 → 빌드 실패 (PR만)

git tag v* push
  └─ release.yml 실행
       ├─ build-dll        dll 빌드
       ├─ build-frontend   프로덕션 빌드
       ├─ publish-pypi     PyPI 배포
       └─ create-release   GitHub Release + dll zip 첨부
```
