# gdep CI/CD 整合指南

> 如何將 gdep 整合到你的 Unity / UE5 專案 GitHub 儲存庫中。
> 所有範例均可直接複製貼上使用。

---

## 核心概念速覽

| 術語 | 含義 |
|------|------|
| **CI** | 每次提交 PR 時自動檢查「這段程式碼沒問題嗎？」 |
| **CD** | 推送版本標籤時自動部署 |
| **閘控** | 檢查失敗時阻止 PR 合併的機制 |

---

## 情境 1 — Unity 專案 PR 閘控

每次 PR 時，gdep 會檢查是否引入了**新的循環相依**。
若發現循環相依，PR 合併按鈕會變紅。

```yaml
# .github/workflows/gdep-gate.yml  （加入你的 Unity 儲存庫）
name: gdep Quality Gate

on:
  pull_request:
    branches: [ main, master, develop ]
    paths:
      - 'Assets/Scripts/**'   # 僅在 Scripts 資料夾變更時觸發

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

      - name: Check for new circular dependencies
        run: |
          gdep diff Assets/Scripts --commit HEAD~1 --fail-on-cycles
```

---

## 情境 2 — UE5 專案 + Lint 報告

每次 PR 時掃描反模式（Tick 內 SpawnActor、缺少 Super:: 等），
並將結果儲存為 **JSON 成品**，可在 Actions 標籤頁下載。

```yaml
# .github/workflows/gdep-gate.yml  （UE5 版）
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
          python3 -c "
          import json, sys
          d = json.load(open('lint-report.json'))
          errors = [x for x in d if x.get('severity') == 'Error']
          warnings = [x for x in d if x.get('severity') == 'Warning']
          print(f'Issues: {len(d)} total, {len(errors)} errors, {len(warnings)} warnings')
          if errors:
              for e in errors: print(f'  ERROR [{e[\"rule_id\"]}]: {e[\"class_name\"]} — {e[\"message\"]}')
              sys.exit(1)
          "

      - name: Upload lint report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: gdep-lint-report
          path: lint-report.json
```

---

## 情境 3 — gdep 自身發布（版本標籤 → PyPI 自動部署）

```bash
# 只需推送標籤，release.yml 會自動處理一切。
git tag v0.2.0
git push origin v0.2.0
# 自動執行：構建 gdep.dll → 構建前端 → 上傳到 PyPI → 建立 GitHub Release
```

### 註冊 PyPI Token

1. 在 https://pypi.org 產生 API token
2. GitHub 儲存庫 → Settings → Secrets and variables → Actions
3. 以 `PYPI_API_TOKEN` 為名新增
4. 在 `release.yml` 中取消 `password:` 行的註解

> **OIDC Trusted Publishing** 方式無需 token 即可部署。

---

## CI 徽章（加入 README）

```markdown
[![CI](https://github.com/pirua-game/gdep/actions/workflows/ci.yml/badge.svg)](https://github.com/pirua-game/gdep/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/gdep)](https://pypi.org/project/gdep/)
```

---

## 可偵測的 Lint 規則（13 條）

| 規則 ID | 引擎 | 說明 | 嚴重程度 |
|---------|------|------|---------|
| `UNI-PERF-001` | Unity | Update 內呼叫 GetComponent/Find | Error |
| `UNI-PERF-002` | Unity | Update 內 new/Instantiate 配置 | Error |
| `UNI-ASYNC-001` | Unity | Coroutine while(true) 內無 yield | Error |
| `UNI-ASYNC-002` | Unity | Coroutine 內 FindObjectOfType/Resources.Load | Warning |
| `UE5-PERF-001` | UE5 | Tick 內 SpawnActor/LoadObject | Error |
| `UE5-PERF-002` | UE5 | BeginPlay 內同步 LoadObject | Warning |
| `UE5-BASE-001` | UE5 | 缺少 Super:: 呼叫 | Warning |
| `UE5-GAS-001` | UE5 | ActivateAbility() 內缺少 CommitAbility() | Error |
| `UE5-GAS-002` | UE5 | GAS Ability 內高代價 world 查詢 | Warning |
| `UE5-GAS-003` | UE5 | BlueprintCallable 超過 10 個 | Info |
| `UE5-GAS-004` | UE5 | BlueprintPure 方法缺少 const | Info |
| `UE5-NET-001` | UE5 | Replicated 屬性無 ReplicatedUsing 回呼 | Info |
| `GEN-ARCH-001` | 通用 | 循環相依 | Warning |

---

## 流程概覽

```
開啟 PR
  └─ ci.yml 執行
       ├─ build-dll        建置 C# dll
       ├─ lint-python      Python 程式碼品質
       ├─ build-frontend   TypeScript 建置驗證
       ├─ test-linux       煙霧測試
       ├─ test-windows     煙霧測試
       └─ gate-cycles      新循環相依 → 建置失敗（僅 PR）

推送 git tag v*
  └─ release.yml 執行
       ├─ build-dll        建置 dll
       ├─ build-frontend   正式建置
       ├─ publish-pypi     發布至 PyPI
       └─ create-release   建立 GitHub Release + 附加 dll zip
```
