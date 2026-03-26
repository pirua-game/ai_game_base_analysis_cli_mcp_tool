# 🎮 gdep — 游戏代码库分析工具

**在 0.5 秒内理解 Unity/UE5/Axmol 大型项目，让 Claude/Cursor 真正读懂代码**

[![CI](https://github.com/pirua-game/gdep/actions/workflows/ci.yml/badge.svg)](https://github.com/pirua-game/gdep/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/gdep)](https://pypi.org/project/gdep/)
[![npm](https://img.shields.io/npm/v/gdep-mcp)](https://www.npmjs.com/package/gdep-mcp)

> *"修改这个类会影响哪里？"* — 3 秒精确回答，零幻觉
> 实测：**MCP 准确率 100% (5/5)** — 基于代码的事实 vs 普通 Claude 猜测 + 幻觉

**其他语言版本：**
[English](./README.md) · [한국어](./README_KR.md) · [日本語](./README_JA.md) · [繁體中文](./README_ZH_TW.md)

---

## ✨ 为什么要用 gdep？

大型游戏客户端令人痛苦：

- UE5 300 个以上 Blueprint → *"这个 Ability 从哪里被调用？"* — 半天时间消失
- Unity 50 个 Manager + Prefab 引用 → 重构时循环依赖爆发
- *"修改这个类会导致什么崩溃？"* — 手动查找 30 分钟

**gdep 在 0.5 秒内解决这一切。**

### 实测性能指标

| 指标 | 数值 | 备注 |
|------|------|------|
| UE5 热缓存扫描 | **0.46 秒** | 2,800+ uasset 项目 |
| Unity 热缓存扫描 | **0.49 秒** | SSD 环境，900+ 个类 |
| 峰值内存 | **28.5 MB** | 目标 10 倍余量 |
| MCP 准确率 | **5/5 (100%)** | 基于代码的事实 |

> 详情 → [docs/BENCHMARK_ZH.md](./docs/BENCHMARK_ZH.md) · [docs/mcp-benchmark_ZH.md](./docs/mcp-benchmark_ZH.md)

---

## 🤖 MCP 集成 — 让 AI 读懂真实代码

gdep 为 Claude Desktop、Cursor 等 MCP 兼容 AI Agent 提供 MCP 服务器。

### 一行安装

```bash
npm install -g gdep-mcp
```

### Agent 配置（复制粘贴）

```json
{
  "mcpServers": {
    "gdep": {
      "command": "gdep-mcp",
      "env": { "PYTHONUTF8": "1" }
    }
  }
}
```

配置完成。Claude · Cursor · Gemini 每次对话都可使用 **19 个**游戏引擎专属工具。

### MCP 改变什么

```
普通 Claude: "CombatCore 可能有一些 Manager 依赖..." ← 猜测
gdep MCP:   直接依赖 2 个 · 间接 200+ UI 类 · 资源: prefabs/UI/combat.prefab
```

### 19 个 MCP 工具一览

| 工具 | 使用时机 |
|------|---------|
| `get_project_context` | **始终最先调用** — 项目整体概览 |
| `analyze_impact_and_risk` | 修改类前的安全确认（`detail_level="summary"` 快速摘要） |
| `explain_method_logic` | 单个方法内部控制流摘要 — Guard/Branch/Loop/Always |
| `trace_gameplay_flow` | C++ → Blueprint 调用链追踪 |
| `inspect_architectural_health` | 技术债务全面诊断 |
| `explore_class_semantics` | 陌生类深度分析 |
| `suggest_test_scope` | 修改类后需要运行的测试文件自动推算 |
| `suggest_lint_fixes` | lint 问题 + 代码修复建议（dry-run） |
| `summarize_project_diff` | 从架构角度汇总 git diff |
| `get_architecture_advice` | 项目综合诊断 + LLM 架构建议 |
| `execute_gdep_cli` | CLI 全功能直接访问 |
| `find_unity_event_bindings` | Inspector 绑定方法（代码搜索不到的区域） |
| `analyze_unity_animator` | Animator 状态机结构 |
| `analyze_axmol_events` | Axmol EventDispatcher/Scheduler 绑定映射 |
| `analyze_ue5_gas` | GAS Ability / Effect / Tag / ASC 全量 — 包含**置信度标头** + IS-A 资产角色分类 |
| `analyze_ue5_behavior_tree` | BehaviorTree 资源结构 |
| `analyze_ue5_state_tree` | StateTree 资源结构 |
| `analyze_ue5_animation` | ABP 状态 + Montage + GAS Notify |
| `analyze_ue5_blueprint_mapping` | C++ 类 → Blueprint 实现映射 — 包含**置信度标头** |

### UE5 置信度透明化

每个 UE5 分析响应的顶部均包含：
```
> Confidence: **MEDIUM** | Coverage: 4633/4633 (100.0%) | UE version: 5.6 (validated)
```
`gdep init` 生成的 `.gdep/AGENTS.md` 提供各置信等级对应的 AI Agent 行为指南。

> 详细配置 → [gdep-cli/gdep_mcp/README_ZH.md](./gdep-cli/gdep_mcp/README_ZH.md)

---

## 📦 安装

| 项目 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | CLI · MCP 服务器 |
| .NET Runtime | 8.0+ | C# / Unity 项目分析 |

```bash
# Windows
install.bat

# macOS / Linux
chmod +x install.sh && ./install.sh
```

---

## 🚀 快速开始

```bash
gdep detect {path}                     # 自动检测引擎
gdep scan {path} --circular --top 15   # 结构分析
gdep init {path}                       # 生成 .gdep/AGENTS.md
gdep advise {path}                     # 架构诊断 + 建议
```

---

## 🖥️ Web UI — 在浏览器中可视化分析

安装完成后无需终端，直接在浏览器中查看依赖图、调用流程并使用 AI 聊天。

**第一步 — 安装**（在项目根目录执行一次）

```
install.bat          # Windows
./install.sh         # macOS / Linux
```

**第二步 — 启动**

```
run.bat              # Windows — 自动在两个独立终端中启动后端 + 前端
./run.sh             # macOS/Linux — 终端 1：后端  (http://localhost:8000)
./run_front.sh       # macOS/Linux — 终端 2：前端 (http://localhost:5173)
```

打开 `http://localhost:5173` → 在侧边栏中指定项目源代码目录

主要功能：
- 交互式依赖图与调用流程可视化
- 类浏览器（含影响分析与 lint）
- 读取实际代码的 AI 聊天智能体（工具调用）
- 引擎专属探索器：GAS · Blueprint 映射 · Animator · BehaviorTree · StateTree

> UI 语言：**仅支持英语和韩语** · 本地 LLM：支持 **Ollama** · 非商业工具，部分功能可能尚不完善

详细文档 → [gdep-cli/web/README.md](./gdep-cli/web/README.md)

---

## 🎯 命令参考

| 命令 | 说明 | 使用时机 |
|------|------|---------|
| `detect` | 自动检测引擎类型 | 首次分析前 |
| `scan` | 耦合度·循环引用·死代码 | 了解结构、重构前 |
| `describe` | 类详情 + Blueprint 实现 + AI 摘要 | 陌生类、代码审查 |
| `flow` | 调用链追踪（C++→BP 边界） | Bug 追踪、流程分析 |
| `impact` | 变更影响范围反向追踪 | 重构前安全确认 |
| `test-scope` | 修改类后应运行的测试文件 | 合并前、CI 规划 |
| `watch` | 实时文件变更监视 (impact+test+lint) | 开发中持续监控 |
| `lint` | 16 条游戏专用反模式（+ `--fix`） | PR 前质量检查 |
| `advise` | 整体架构诊断 + LLM 建议 | 架构审查、技术债务 |
| `graph` | 依赖关系图导出 | 文档化、可视化 |
| `diff` | 提交前后依赖对比 | PR 审查、CI 门控 |
| `init` | 生成 AI Agent 上下文 | **AI 编码助手初始设置** |
| `context` | 输出项目上下文 | 复制到 AI 对话 |
| `hints` | 管理单例提示 | 提升 flow 准确度 |
| `config` | LLM 配置 | 使用 AI 摘要前 |

---

## 🎮 支持的引擎

| 引擎 | 类分析 | 流程分析 | 反向引用 | 专项功能 |
|------|--------|---------|---------|---------|
| Unity (C#) | ✅ | ✅ | ✅ Prefab/Scene | UnityEvent、Animator |
| Unreal Engine 5 | ✅ UCLASS/USTRUCT/UENUM | ✅ C++→BP | ✅ Blueprint/Map | GAS、BP 映射、BT/ST、ABP/Montage |
| Axmol / Cocos2d-x (C++) | ✅ Tree-sitter | ✅ | — | EventDispatcher/Scheduler 绑定 |
| .NET (C#) | ✅ | ✅ | — | |
| 通用 C++ | ✅ | ✅ | — | |

---

*MCP 服务器 → [gdep-cli/gdep_mcp/README_ZH.md](./gdep-cli/gdep_mcp/README_ZH.md)*
*CI/CD 集成 → [docs/ci-integration_ZH.md](./docs/ci-integration_ZH.md)*
*性能基准 → [docs/BENCHMARK_ZH.md](./docs/BENCHMARK_ZH.md)*
