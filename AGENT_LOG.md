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

## 2026-08-02 — 反馈闭环接入主循环（修正工程缺口）

### Task: T4.1 增强 — 策略状态机真正驱动 agent loop 多轮自我修正

| 字段 | 内容 |
|------|------|
| **Superpowers 技能** | `requesting-code-review`（自评发现）→ `test-driven-development` |
| **触发** | 项目质量评审中发现：`_process_test_results` 每次测试失败都调 `initialize`，`record_attempt` 在 `agent_loop` 中从未被调用——状态机的 3 次切换 / 6 次上报阈值在真实自主 loop 中永不触发，只在 demo/tests 手动驱动。重点维度的深度机制"造好了、测了、演示了，但没插进流水线通电"。 |
| **关键修改** | ① `run()` 起始重置 `_correction_ctx`/`_feedback_ctx`，每任务干净起步 ② `_process_test_results` 改为跨 turn 有状态：首次失败 `initialize`，后续失败 `record_attempt(success=False)` 推进状态机（attempt 计数 / 连续失败切换 / 6 次阈值），状态机进入 `MAX_RETRIES_REACHED`/`STRATEGY_EXHAUSTED`/`USER_INTERVENTION` 时 `self._state = PAUSED` 真正停下上报；测试通过且修正进行中时 `record_attempt(success=True)` 标记 `SUCCEEDED` ③ 新增 `TestFeedbackMultiRound`：`test_repeated_failures_escalate_and_pause`（8 轮失败 → PAUSED + 上报态）、`test_failure_then_pass_records_success`（失败后通过 → SUCCEEDED） |
| **验证** | 全量 `pytest tests/` → **328 passed**（原 326 + 新增 2），无回归。mock LLM 下可确定性验证"agent 收到失败反馈后据状态机推进、阈值后停下上报、恢复后标记成功"——§A.6-② 从单次层面提升到真·多轮闭环层面 |
| **Commit** | 见本次提交 |
| **人工干预** | 是。此改动由人工评审发起、人工编写实现与测试，非 subagent 产出。状态机自身实现（T3.3）未改动，仅将其接入主循环 |
| **教训** | "机制存在 + 机制被单测" ≠ "机制在真实流水线里被驱动"。重点维度的深度必须验证它接入主循环后仍按预期工作——这正是 §A.4-C "移除 LLM 后机制还能用单测验证"在闭环层面的真实考场 |

---

## 2026-08-02 — Phase H：代码审计修复（诚实性补强）

### Task: 修复"机制假装工作"与若干真实 bug

| 字段 | 内容 |
|------|------|
| **Superpowers 技能** | `requesting-code-review` → `test-driven-development` |
| **触发** | 对全项目做一次客观代码审计，发现若干"看起来能跑、实际未实现或会出错"的点位：① 5 条 CLI 命令是 stub（`config model set` 不持久化、`tool enable/disable` 只 echo、`status`/`cancel` 硬编码、`run --plan-only` 输出固定 4 步树）② WebUI 硬编码 `MockLLMClient`，从 UI 永远跑不到真实 LLM ③ `/run` 返回空 `session_id`（竞态）④ 跨线程 WebSocket 广播用 `new_event_loop` 不安全 ⑤ session 恢复把 `feedback_ctx`/`correction_ctx` 序列化为 `None`，中断后丢失修正历史 ⑥ `VectorStore` 默认不持久化（跨会话记忆不成立）+ ChromaDB 分数尺度与 InMemoryStore 不可比 ⑦ `_detect_completion` 靠子串匹配，"I am not finished yet" 会被误判为完成 ⑧ `original_code=""` 让回灌器名义不符实 |
| **关键修改** | ① CLI：`config model set` 持久化、`tool enable/disable` 持久化到 `.codingkit/config.yaml` 的 `disabled_tools` 并被 `ToolRegistry`/`ContextBuilder`/`AgentLoop` 真正尊重（禁用工具从工具定义中剔除、执行时拒绝且优先于护栏）、`status` 查询 config+最近会话+工具数、`cancel` 诚实说明前台无任务、`_generate_plan` 改为调用真实 LLM 生成计划（无 key 时诚实提示而非伪装）；新增 `_build_llm_client` 让 `codingkit run` 也能用真实 LLM ② WebUI：新增 `_build_web_llm` 读 config+keychain 构建真实 client（无 key 降级 mock），`/run` 在请求线程内预构造 loop 以返回真实 `session_id`，`ConnectionManager` 增加 `broadcast_threadsafe`（`run_coroutine_threadsafe` 调度到主 loop），应用项目 `disabled_tools` ③ session_manager：实现 `_correction_ctx_to/from_dict`、`_feedback_ctx_to/from_dict`、`_test_result_to/from_dict`、`_classification_to/from_dict`，`restore_loop` 恢复修正/反馈状态机；`_toolcall_from_dict` 忽略未知键，修复 `ToolCall(**tc)` 脆弱性 ④ `VectorStore` 默认 `persist_directory=~/.codingkit/chroma`（SPEC §3.6 跨会话记忆真正持久化），ChromaDB 分数改为 `max(0, 1 - distance/2)` 与 InMemoryStore 的 [0,1] cosine 相似度可比 ⑤ `_detect_completion` 改为"文本结尾匹配完成短语"（剥去末尾标点），杜绝"I am not finished yet"误判 ⑥ `_process_test_results` 用 `_last_written_code` 从本轮 `write_file`/`edit_file` 调用回填 `original_code`，回灌器真正包含失败代码 |
| **验证** | 新增 `tests/test_fixes.py`（14 个回归测试：持久化、注册表禁用、解析器不误判、session 修正上下文往返、向量持久化默认值）。全量 `pytest tests/` → **343 passed**（原 329 + 新增 14），`ruff check` 全过，3 个 demo 全过，无回归 |
| **人工干预** | 是。此轮改动由人工审计发起、人工编写实现与测试，非 subagent 产出。审计由一个独立 Explore agent 阅读全部未审源文件后给出 file:line 级问题清单，人工据此逐项修复并补测试 |
| **教训** | "能跑过的测试" ≠ "机制真正工作"。原测试覆盖了各模块的接口层，却没覆盖"CLI 命令是否真的持久化""WebUI 是否真的接了 LLM""session 恢复是否真的保住状态"这类集成层断言。审计 + 回归测试是补这条缝隙的唯一手段。诚实性（stub 标注为 stub、或干脆实现掉）在本作业 §A.4 "机制必须是代码不能是提示词/摆设"的红线意义上，与功能正确性同等重要 |

---

## 2026-08-02 — Phase I：接入国产 LLM provider

### Task: 支持 DeepSeek / GLM / Kimi / MiniMax / Qwen 五家 provider

| 字段 | 内容 |
|------|------|
| **Superpowers 技能** | `writing-plans` → `test-driven-development` |
| **触发** | 实测时 `codingkit config model set deepseek-v4-flash` 被拒："not a recognised model prefix"。根因两层：CLI 的 `known_prefixes` 与 `llm_factory` 都只认 `claude/gpt/o1/o3/o4/mock`，且 `OpenAIClient` 硬编码 `openai.OpenAI(api_key=...)` 不接受 `base_url`，无法指向第三方 endpoint |
| **关键修改** | ① `OpenAIClient.__init__` 增加 `base_url: Optional[str]`，`_ensure_client` 透传给 `openai.OpenAI(api_key=..., base_url=...)`（None 时 SDK 默认 OpenAI，完全向后兼容）② `llm_factory.py` 引入 `PROVIDERS` 表（每条 `(prefixes, label, base_url, models)`），按前缀路由到 `OpenAIClient(base_url=...)`；Kimi 同时认 `kimi` / `moonshot` 两个前缀；导出 `known_prefixes()` / `list_known_models()` 作为 CLI 的单一数据源 ③ `cli/main.py` 的 `model_set` 前缀检查改为大小写不敏感（provider 模型名大小写不一，如 `MiniMax-M1`），`model_list` 目录与 `known_prefixes` 全部从工厂派生，消除硬编码 ④ 测试：`test_llm_client.py` 加 14 个用例（10 参数化 provider 路由 + base_url 透传/省略 + 未知前缀 ValueError），`test_fixes.py` 加 7 个 CLI 验收用例（每家 provider 各一个 + 目录显示 8 组） |
| **验证** | 全量 `pytest tests/` → **364 passed**（原 343 + 新增 21），`ruff check` 全过。CLI 烟测：5 家 provider 模型均可 `config model set` 并持久化；任意 `deepseek-v4-flash` 因前缀路由也被接受；未知 `llama-3` 仍诚实拒绝；`config model list` 显示 8 个 provider 组 |
| **人工干预** | 是。需求由人工提出（接入 5 家国产 provider），实现与测试由人工编写，非 subagent 产出 |
| **教训** | 五家国产 provider 都走 OpenAI 兼容协议，所以正确做法是"一个可配置 `base_url` 的 `OpenAIClient` + 前缀→endpoint 路由表"，而不是写 5 个 client 类——复用比新增更值钱。前缀路由（而非模型名白名单）让 provider 新发模型无需改代码即可用，符合"机制要面向未来扩展"的取向。但各家对 OpenAI `tools`（function-calling）支持程度不一，harness 始终发 OpenAI 格式工具定义，不支持的 provider 会在运行时报错而非静默降级——诚实优于假装兼容 |

---

## 2026-08-03 — Phase J：真实 LLM 端到端验证

### Task: 对真实 DeepSeek 跑通 harness + 已知非确定性 400 定位

| 字段 | 内容 |
|------|------|
| **Superpowers 技能** | `requesting-code-review`（实测驱动） |
| **触发** | Phase I 接入五家国产 provider 后，需实证 harness 在真实 LLM 下真的能转（之前所有运行都是 MockLLMClient，从未对真实 provider 跑过） |
| **过程** | 配 DeepSeek key + `deepseek-v4-flash` 模型后，依次撞见三类错并逐一定位：① 401 `Authentication Fails, Your api key: ****FjJy is invalid` → key 失效，重录 ② 403 `type: forbidden / Request not allowed` → **非 key 问题，是 config 在错的目录**：`codingkit config status` 在 `D:\zuomian\test` 显示 `deepseek-v4-flash`，但 `codingkit run` 在项目目录跑，那边 `.codingkit/config.yaml` 还是默认 `claude-sonnet-5` → 工厂路由到 `ClaudeClient` → 把 DeepSeek key 发给 Anthropic → Anthropic 回 403。`.codingkit/config.yaml` 是按工作目录生效的（项目级配置），不是全局——这是踩坑点 ③ 400 `Messages with role 'tool' must be a response to a preceding message with 'tool_calls'` → DeepSeek 真实返回，**非确定性**（不同任务、不同 LLM 回复模式，只有特定消息序列触发），两次成功运行（排序算法 4 轮、multiply+测试 4 轮）未触发，未能复现捕获 |
| **关键修改** | ① 给 `OpenAIClient.generate` 加 `CODINGKIT_DEBUG=1` 环境变量门控的调试钩子：请求被 provider 拒时，把完整 payload（messages+tools，**不含 key**）打印到 stderr 并写入运行目录 `.codingkit_debug_payload.json`，作为那个非确定性 400 的唯一可靠捕获手段 ② 诊断期间写过的 `diag*.py` scratch 脚本（含真实 key，已 gitignore）在收尾时删除 ③ 加 `.gitignore` 条目：`diag*.py` / `*.local.py` / `.codingkit_debug_payload.json` |
| **验证** | 真实 DeepSeek 端到端跑通两次：a) "写一个高效排序算法" → 3 轮 2 工具调用，生成 `efficient_sort.py`（三数取中快排 + 插入排序阈值 + Hoare 分区 + 尾递归优化）并通过测试 b) "Add a multiply function to calc.py with tests" → 4 轮 4 工具调用，生成 `multiply` 函数 + 5 个测试全过。`pytest tests/` 仍 364 passed，`ruff` 全过。**harness 的反馈闭环、工具调度、状态机在真实 provider 下实证可用**——补上了 Phase H 之前"从未对真实 provider 跑过"的豁免项 |
| **已知未解决** | DeepSeek 偶发的 400 `tool 消息前无 tool_calls`：非确定性，MockLLMClient 复现的序列均合法，两次真实成功运行也未触发，根因未定位。疑似 `OpenAIClient` 在某类消息模式（如 LLM 同时返回 text + tool_calls、或多 tool_call 拆分）下产出的序列被 DeepSeek 拒。`CODINGKIT_DEBUG=1` 钩子已就位，待下次复现时捕获 payload 后定点修 `_messages_to_openai` |
| **人工干预** | 是。实测 + 诊断 + 调试钩子由人工驱动 |
| **教训** | **"config 是项目级、按目录生效"** 这条没在文档里讲清楚，导致 403 误判为账号问题排查了很久。配置作用域（全局 vs 项目级）必须在 README 显式说明。另外：真实 provider 的非确定性错误（受温度/回复模式影响）极难靠重试复现，必须有"出错即落盘 payload"的可观测钩子才能定位——这正是 §A.4-C"机制可观测"在排障场景的延伸。诚实记录"已实证可用 + 有一个未复现的非确定性 bug + 有捕获手段"，比假装全绿更符合本作业的红线 |

---

## 统计数据

| 指标 | 数值 |
|------|------|
| **总 commit 数** | 40（含 6 个 merge commit） |
| **总 PR 数** | 6 |
| **总测试数** | 364（全部通过，不依赖真实 LLM） |
| **CLI 命令数** | 19（SPEC §3.1 的 18 条 + `config status`） |
| **subagent worktree 数** | 4（冷启动 + T2.2 + T2.3 + T3.1） |
| **人工 PR worktree 数** | 4（WebUI 后端/前端/分发/文档） |
| **人工干预次数** | 5（pyproject.toml 警告过滤 + .gitignore 前端排除 + 审计修复轮 + 国产 provider 接入 + 真实 LLM 实测定位） |
| **冷启动验证** | 4 个 task，暴露 1 个 block 级别 SPEC 缺陷 |