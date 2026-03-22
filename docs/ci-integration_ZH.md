# gdep CI/CD 集成指南

> 如何将 gdep 集成到你的 Unity / UE5 项目 GitHub 仓库中。
> 所有示例均可直接复制粘贴使用。

---

## 核心概念速览

| 术语 | 含义 |
|------|------|
| **CI** | 每次提交 PR 时自动检查"这段代码没问题吗？" |
| **CD** | 推送版本标签时自动部署 |
| **门控** | 检查失败时阻止 PR 合并的机制 |

---

## 场景 1 — Unity 项目 PR 门控

每次 PR 时，gdep 会检查是否引入了**新的循环依赖**。
如果发现循环依赖，PR 合并按钮会变红。

```yaml
# .github/workflows/gdep-gate.yml  （添加到你的 Unity 仓库）
name: gdep Quality Gate

on:
  pull_request:
    branches: [ main, master, develop ]
    paths:
      - 'Assets/Scripts/**'   # 仅在 Scripts 文件夹变更时触发

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

## 场景 2 — UE5 项目 + Lint 报告

每次 PR 时扫描反模式（Tick 内 SpawnActor、缺少 Super:: 等），
并将结果保存为 **JSON 制品**，可在 Actions 标签页下载。

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
          # 规则：UE5-GAS-001（缺少 CommitAbility）、UE5-BASE-001（缺少 Super）
          #       UE5-GAS-002（高代价查询）、UE5-NET-001（缺少 ReplicatedUsing）等
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

## 场景 3 — gdep 自身发布（版本标签 → PyPI 自动部署）

用于发布 gdep 新版本时使用。

```bash
# 1. CI 流水线会自动从标签覆写 pyproject.toml 中的版本号，无需手动修改。

# 2. 只需推送标签，release.yml 会自动处理一切。
git tag v0.2.0
git push origin v0.2.0

# 自动执行：
#   1. 构建 gdep.dll
#   2. 构建前端
#   3. 上传包到 PyPI
#   4. 创建 GitHub Release + 附加 dll zip
```

### 注册 PyPI Token

1. 在 https://pypi.org 生成 API token
2. GitHub 仓库 → Settings → Secrets and variables → Actions
3. 以 `PYPI_API_TOKEN` 为名添加
4. 在 `release.yml` 中取消 `password:` 行的注释

> **OIDC Trusted Publishing** 方式无需 token 即可部署。
> 在 PyPI 项目设置中将你的 GitHub 仓库注册为可信发布者即可。

---

## CI 徽章（添加到 README）

```markdown
[![CI](https://github.com/pirua-game/gdep/actions/workflows/ci.yml/badge.svg)](https://github.com/pirua-game/gdep/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/gdep)](https://pypi.org/project/gdep/)
```

---

## 可检测的 Lint 规则（13 条）

| 规则 ID | 引擎 | 说明 | 严重级别 |
|---------|------|------|---------|
| `UNI-PERF-001` | Unity | Update 中调用 GetComponent/Find | Error |
| `UNI-PERF-002` | Unity | Update 中 new/Instantiate 分配 | Error |
| `UNI-ASYNC-001` | Unity | Coroutine while(true) 中无 yield | Error |
| `UNI-ASYNC-002` | Unity | Coroutine 内 FindObjectOfType/Resources.Load | Warning |
| `UE5-PERF-001` | UE5 | Tick 中 SpawnActor/LoadObject | Error |
| `UE5-PERF-002` | UE5 | BeginPlay 中同步 LoadObject | Warning |
| `UE5-BASE-001` | UE5 | 缺少 Super:: 调用 | Warning |
| `UE5-GAS-001` | UE5 | ActivateAbility() 中缺少 CommitAbility() | Error |
| `UE5-GAS-002` | UE5 | GAS Ability 内高代价 world 查询 | Warning |
| `UE5-GAS-003` | UE5 | BlueprintCallable 超过 10 个 | Info |
| `UE5-GAS-004` | UE5 | BlueprintPure 方法缺少 const | Info |
| `UE5-NET-001` | UE5 | Replicated 属性无 ReplicatedUsing 回调 | Info |
| `GEN-ARCH-001` | 通用 | 循环依赖 | Warning |

---

## 流程概览

```
打开 PR
  └─ ci.yml 运行
       ├─ build-dll        构建 C# dll
       ├─ lint-python      Python 代码质量检查
       ├─ build-frontend   TypeScript 构建验证
       ├─ test-linux       冒烟测试
       ├─ test-windows     冒烟测试
       └─ gate-cycles      新循环依赖 → 构建失败（仅 PR）

推送 git tag v*
  └─ release.yml 运行
       ├─ build-dll        构建 dll
       ├─ build-frontend   生产构建
       ├─ publish-pypi     发布到 PyPI
       └─ create-release   创建 GitHub Release + 附加 dll zip
```
