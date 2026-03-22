# gdep CI/CD Integration Guide

> How to add gdep to your Unity / UE5 project's GitHub repository.
> All examples are copy-paste ready.

---

## One-Line Concept

| Term | Meaning |
|------|---------|
| **CI** | Automatically checks "is this code okay?" on every PR |
| **CD** | Automatically deploys when a version tag is pushed |
| **Gate** | Blocks PR merges when a check fails |

---

## Scenario 1 — Unity Project PR Gate

On every PR, gdep checks whether **new circular dependencies** were introduced.
If a cycle is found, the PR merge button turns red.

```yaml
# .github/workflows/gdep-gate.yml  (add to your Unity repo)
name: gdep Quality Gate

on:
  pull_request:
    branches: [ main, master, develop ]
    paths:
      - 'Assets/Scripts/**'   # only runs when Scripts folder changes

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

## Scenario 2 — UE5 Project + Lint Report

On every PR, scans for anti-patterns (SpawnActor in Tick, missing Super::, etc.)
and saves results as a **JSON artifact** — downloadable from the Actions tab.

```yaml
# .github/workflows/gdep-gate.yml  (UE5 version)
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
          # Rules: UE5-GAS-001 (missing CommitAbility), UE5-BASE-001 (missing Super),
          #        UE5-GAS-002 (expensive queries), UE5-NET-001 (missing ReplicatedUsing), etc.
          if errors:
              for e in errors: print(f'  ERROR [{e[\"rule_id\"]}]: {e[\"class_name\"]} — {e[\"message\"]}')
              sys.exit(1)
          "

      - name: Upload lint report
        if: always()   # save artifact even on failure
        uses: actions/upload-artifact@v4
        with:
          name: gdep-lint-report
          path: lint-report.json
```

---

## Scenario 3 — gdep Self-Release (version tag → PyPI auto-deploy)

Used when releasing a new version of gdep itself.

```bash
# 1. The CI pipeline overwrites pyproject.toml version from the tag automatically.
#    No manual version bump needed.

# 2. Just push a tag — release.yml handles everything.
git tag v0.2.0
git push origin v0.2.0

# What happens automatically:
#   1. Build gdep.dll
#   2. Build frontend
#   3. Upload package to PyPI
#   4. Create GitHub Release + attach dll zip
```

### Registering a PyPI Token

1. Generate an API token at https://pypi.org
2. Go to GitHub repo → Settings → Secrets and variables → Actions
3. Add as `PYPI_API_TOKEN`
4. Uncomment the `password:` line in `release.yml`

> **OIDC Trusted Publishing** lets you deploy without a token.
> Register your GitHub repo as a trusted publisher in your PyPI project settings.

---

## CI Badge (add to your README)

```markdown
[![CI](https://github.com/pirua-game/gdep/actions/workflows/ci.yml/badge.svg)](https://github.com/pirua-game/gdep/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/gdep)](https://pypi.org/project/gdep/)
```

---

## Detectable Lint Rules (13)

| Rule ID | Engine | Description | Severity |
|---------|--------|-------------|----------|
| `UNI-PERF-001` | Unity | GetComponent/Find in Update | Error |
| `UNI-PERF-002` | Unity | new/Instantiate allocation in Update | Error |
| `UNI-ASYNC-001` | Unity | Coroutine while(true) without yield | Error |
| `UNI-ASYNC-002` | Unity | FindObjectOfType/Resources.Load inside Coroutine | Warning |
| `UE5-PERF-001` | UE5 | SpawnActor/LoadObject in Tick | Error |
| `UE5-PERF-002` | UE5 | Synchronous LoadObject in BeginPlay | Warning |
| `UE5-BASE-001` | UE5 | Missing Super:: call | Warning |
| `UE5-GAS-001` | UE5 | Missing CommitAbility() in ActivateAbility() | Error |
| `UE5-GAS-002` | UE5 | Expensive world query in GAS Ability | Warning |
| `UE5-GAS-003` | UE5 | Excessive BlueprintCallable (>10) | Info |
| `UE5-GAS-004` | UE5 | Missing const on BlueprintPure method | Info |
| `UE5-NET-001` | UE5 | Replicated property without ReplicatedUsing callback | Info |
| `GEN-ARCH-001` | Common | Circular dependency | Warning |

---

## Flow Summary

```
PR opened
  └─ ci.yml runs
       ├─ build-dll        Build C# dll
       ├─ lint-python      Python code quality
       ├─ build-frontend   TypeScript build check
       ├─ test-linux       Smoke test
       ├─ test-windows     Smoke test
       └─ gate-cycles      New circular dep → build fails (PRs only)

git tag v* pushed
  └─ release.yml runs
       ├─ build-dll        Build dll
       ├─ build-frontend   Production build
       ├─ publish-pypi     Deploy to PyPI
       └─ create-release   GitHub Release + dll zip attached
```
