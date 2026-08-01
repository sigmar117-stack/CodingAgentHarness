# CodingKit — AGENT_LOG 过程日志

> 按时间顺序记录关键节点。每条包含：时间戳与 task 编号、触发的 Superpowers 技能、关键信息、commit hash、人工干预与教训。

---

## 2026-07-29 — 项目初始化

### Task: 初始化 Git 仓库与项目骨架

| 字段 | 内容 |
|------|------|
| **Superpowers 技能** | `brainstorming` → `writing-plans` |
| **触发** | 首次启动智能体，进行 brainstorming |
| **关键信息** | 智能体追问了"反馈闭环具体指什么"、"修正策略做深的方向"等关键问题，帮助将模糊想法转化为四层机制设计 |
| **Commit** | `6cf68a9` — Initial commit（仅 README 占位） |
| **人工干预** | 无。brainstorming 阶段主要做决策，未产生代码 |
| **教训** | brainstorming 技能在追问深度上表现出色，但依赖分组不够精确，导致冷启动验证时卡住 |

---

## 2026-08-01 — 冷启动验证（关键里程碑）

### Task: T1.1 项目脚手架 + T1.2 凭据存储 + T1.3 LLM 抽象层 + T2.1 工具实现

| 字段 | 内容 |
|------|------|
| **Superpowers 技能** | `subagent-driven-development`（冷启动） |
| **智能体** | 第二个 Claude Code 实例（全新 session，不导入历史） |
| **提供的材料** | 仅 `SPEC.md` + `PLAN.md` |
| **关键信息** | 冷启动 agent 自主完成 4 个 task（预期 1-2 个），51 个测试全部通过 |
| **Commit** | `1a988cc` — 冷启动阶段完成 |
| **人工干预** | 无。冷启动 agent 在依赖打包策略和适配器深度上暂停提问，确认后自主推进 |
| **教训** | **冷启动验证的价值被充分验证**：暴露了 SPEC 依赖分组精确度不足的问题（block 级别），如果不发现，正式实现会在 T1.1 卡住 |

---

## 2026-08-01 — Phase B：核心构建

### Task: T2.2 治理护栏

| 字段 | 内容 |
|------|------|
| **Superpowers 技能** | `subagent-driven-development` + `test-driven-development` |
| **智能体** | Claude Code（独立 worktree `agent-a6bc7ab17433fbe03`） |
| **关键信息** | 实现危险动作检测 + HITL 审批状态机。23 个测试通过 |
| **Commit** | `69bf37e` |
| **人工干预** | 无 |
| **教训** | 治理护栏的规则匹配（`rm -rf`、`sudo` 等模式）用确定性代码实现，符合 §A.4-C 的"移除 LLM 后可测"要求 |

### Task: T2.3 记忆管理

| 字段 | 内容 |
|------|------|
| **Superpowers 技能** | `subagent-driven-development` + `test-driven-development` |
| **智能体** | Claude Code（独立 worktree `agent-a9bafabe5f960c07d`） |
| **关键信息** | 实现会话存储（JSON）+ 向量存储（ChromaDB）+ 降级到内存。27 个测试通过 |
| **Commit** | `dfabba3` |
| **人工干预** | 无。subagent 在同一 worktree 上同时完成了 T2.3 的实现和 PLAN 文档更新 |
| **教训** | 向量数据库降级设计是 AI 提出的，避免了 ChromaDB 不可用时系统崩溃 |

---

## 2026-08-01 — Phase C：反馈闭环（主攻方向）

### Task: T3.1 校验器

| 字段 | 内容 |
|------|------|
| **Superpowers 技能** | `subagent-driven-development` + `test-driven-development` |
| **智能体** | Claude Code（独立 worktree `agent-ab6b29543aa14a836`） |
| **关键信息** | 实现 pytest JUnit XML 解析 + 原始输出回退。24 个测试通过 |
| **Commit** | `9574d44` |
| **人工干预** | 无。subagent 直接按 PLAN 完成 |
| **教训** | PLAN 中明确了 run_tests 和校验器的边界划分，subagent 未产生歧义 |

### Task: T3.2 失败分类器

| 字段 | 内容 |
|------|------|
| **Superpowers 技能** | `test-driven-development` |
| **智能体** | Claude Code（主 worktree） |
| **关键信息** | 实现基于优先级的规则引擎，支持 8 种分类 + 置信度计算。34 个测试通过 |
| **Commit** | `1293af3` |
| **人工干预** | 无。规则引擎方案由 AI 在 brainstorming 阶段提出，被采纳 |
| **教训** | 优先级规则引擎是确定性实现，可独立单测，符合核心要求 |

### Task: T3.3 修正策略引擎（主攻深度）

| 字段 | 内容 |
|------|------|
| **Superpowers 技能** | `test-driven-development` |
| **智能体** | Claude Code（主 worktree） |
| **关键信息** | 实现状态机（ATTEMPTING → SUCCEEDED / MAX_RETRIES / EXHAUSTED / USER_INTERVENTION），每种失败分类的策略链，3 次同策略失败自动切换，6 次总失败上报人工，中断恢复。42 个测试通过 |
| **Commit** | `8349222`（docs 标记）+ `ce48f9d`（代码 + demo） |
| **人工干预** | 无。状态机设计完全由 AI 提出方案，人工确认后实现 |
| **教训** | **状态机模式天然适合修正流程**，每一步状态变化可观测，方便 WebUI 展示 |

### Task: T3.4 回灌器

| 字段 | 内容 |
|------|------|
| **Superpowers 技能** | `test-driven-development` |
| **智能体** | Claude Code（主 worktree） |
| **关键信息** | 将修正历史组织为结构化 Markdown 上下文。16 个测试通过 |
| **Commit** | `ce48f9d`（与 T3.3 同次提交） |
| **人工干预** | 无 |
| **教训** | 回灌器是"确定性代码"的典型——没用到任何 LLM，纯文本拼接，但可单测 |

### Task: T7.2 机制演示

| 字段 | 内容 |
|------|------|
| **Superpowers 技能** | `test-driven-development` |
| **智能体** | Claude Code（主 worktree） |
| **关键信息** | 3 个确定性演示脚本：治理护栏拦截、反馈闭环修正、策略状态机深度演示 |
| **Commit** | `ce48f9d` |
| **人工干预** | 无 |
| **教训** | 演示脚本用 Unicode 符号（▶、📌）在 Windows GBK 终端下显示异常，需 `PYTHONIOENCODING=utf-8`。这是平台兼容性问题 |

---

## 2026-08-01 — Phase D：主循环层

### Task: T4.1 Agent 主循环

| 字段 | 内容 |
|------|------|
| **Superpowers 技能** | `test-driven-development` |
| **智能体** | Claude Code（主 worktree） |
| **关键信息** | 实现 ContextBuilder、ResponseParser、AgentLoop 完整主循环。28 个测试通过 |
| **Commit** | `fa7b068` |
| **人工干预** | 无 |
| **教训** | AgentLoop 整合了所有下层模块，接口设计良好——MockLLMClient 注入后可直接单测 |

### Task: T4.2 CLI 实现

| 字段 | 内容 |
|------|------|
| **Superpowers 技能** | `test-driven-development` |
| **智能体** | Claude Code（主 worktree） |
| **关键信息** | 实现 18 条 CLI 命令（run/config/session/tool/web/status/cancel/version）。26 个测试通过 |
| **Commit** | `52250ed` |
| **人工干预** | 无 |
| **教训** | Typer 框架自动生成帮助信息，减少了人工编写文档的工作量 |

### Task: T4.3 会话管理

| 字段 | 内容 |
|------|------|
| **Superpowers 技能** | `test-driven-development` |
| **智能体** | Claude Code（主 worktree） |
| **关键信息** | 实现会话 CRUD、save/restore、中断保存。17 个测试通过 |
| **Commit** | `4e0ad5f` |
| **人工干预** | 无 |

---

## 2026-08-01 — Phase E：WebUI（人工主导 PR 工作流）

### Task: T5.1 WebUI 后端

| 字段 | 内容 |
|------|------|
| **Superpowers 技能** | `subagent-driven-development` + `test-driven-development` + `finishing-a-development-branch` |
| **智能体** | Claude Code（独立 worktree `worktree-webui-backend`） |
| **关键信息** | FastAPI 服务器 + REST API（7 个端点）+ WebSocket 实时推送 + 审批远程模式。20 个测试通过 |
| **Commit** | `087e3f1` → PR #1 |
| **人工干预** | 修复 `pyproject.toml` 的 StarletteDeprecationWarning 过滤配置 |
| **教训** | **人工干预是必要的**：subagent 不会知道本地环境中的 Starlette 版本兼容性问题。这也是"两阶段评审"的意义 |

### Task: T5.2 WebUI 前端

| 字段 | 内容 |
|------|------|
| **Superpowers 技能** | `subagent-driven-development` + `finishing-a-development-branch` |
| **智能体** | Claude Code（独立 worktree `worktree-webui-frontend`） |
| **关键信息** | Vite + React + TypeScript 项目，3 页面（Dashboard/Interactive/History），WebSocket 集成 |
| **Commit** | `88b9b64` → PR #2 |
| **人工干预** | 无。subagent 自动生成了完整的 React 组件 |
| **教训** | 前端构建产物（`node_modules/`、`dist/`）需要用 `.gitignore` 排除，subagent 未自动处理 |

---

## 2026-08-01 — Phase F：分发

### Task: T6.1 Dockerfile + T6.2 PyPI 打包 + T6.3 CI

| 字段 | 内容 |
|------|------|
| **Superpowers 技能** | `subagent-driven-development` + `finishing-a-development-branch` |
| **智能体** | Claude Code（独立 worktree `worktree-distribution-ci`） |
| **关键信息** | 多阶段 Dockerfile + PyPI entry point + GitHub Actions CI（3 个 job） |
| **Commit** | `b26a4db` → PR #3 |
| **人工干预** | 无 |
| **教训** | CI 配置中 `unit-test` job 名称与作业要求一致，但作业要求的是 `.gitlab-ci.yml`，当前使用 GitHub Actions |

---

## 2026-08-01 — Phase G：文档收尾

### Task: README / PLAN / .gitignore 更新

| 字段 | 内容 |
|------|------|
| **Superpowers 技能** | `finishing-a-development-branch` |
| **智能体** | Claude Code（独立 worktree `worktree-docs-cleanup`） |
| **关键信息** | README 从占位符替换为完整文档，PLAN 更新所有 task 状态，.gitignore 添加前端排除 |
| **Commit** | `e36f2e4` → PR #4 |
| **人工干预** | 无 |

---

## 统计数据

| 指标 | 数值 |
|------|------|
| **总 commit 数** | 20（含 4 个 merge commit） |
| **总 PR 数** | 4 |
| **总测试数** | 326（全部通过，不依赖真实 LLM） |
| **subagent worktree 数** | 4（冷启动 + T2.2 + T2.3 + T3.1） |
| **人工 PR worktree 数** | 4（WebUI 后端/前端/分发/文档） |
| **人工干预次数** | 2（pyproject.toml 警告过滤 + .gitignore 前端排除） |
| **冷启动验证** | 4 个 task，暴露 1 个 block 级别 SPEC 缺陷 |