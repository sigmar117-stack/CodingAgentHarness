# CodingKit — PLAN 实现计划

> **说明**: 本文档由 `writing-plans` 技能产出，将 SPEC 分解为可执行的 task 列表。  
> 每个 task 颗粒度 2–5 分钟，可由一个 subagent 在一次会话内完成。  
> 标注了 task 间的依赖关系与可并行部分。

---

## 依赖总图

```
Layer 1 ─── Foundation
  T1.1 ─── 项目脚手架
  T1.2 ─── 凭据存储
  T1.3 ─── LLM 抽象层
     │
Layer 2 ─── Core (可并行)
  T2.1 ─── 工具实现       T2.2 ─── 治理护栏    T2.3 ─── 记忆管理
     │                       │                      │
Layer 3 ─── Feedback Loop (依赖 T2.1)  ✅
  T3.1 ─── 校验器           ✅
  T3.2 ─── 失败分类器        ✅
  T3.3 ─── 修正策略引擎（主攻方向）✅
  T3.4 ─── 回灌器           ✅
     │
Layer 4 ─── Agent Loop (依赖 Layer 2 + 3)  ✅
  T4.1 ─── Agent 主循环       ✅
  T4.2 ─── CLI 实现           ✅
  T4.3 ─── 会话管理           ✅
     │
Layer 5 ─── WebUI (可并行)
  T5.1 ─── FastAPI 后端
  T5.2 ─── React 前端
     │
Layer 6 ─── Distribution (可并行)
  T6.1 ─── Dockerfile
  T6.2 ─── PyPI 打包
  T6.3 ─── GitHub Actions CI
     │
Layer 7 ─── Testing & Demo
  T7.1 ─── Mock LLM 单元测试
  T7.2 ─── 机制演示
```

---

## Layer 1：Foundation（基础层）

### T1.1 项目脚手架

| 字段 | 内容 |
|------|------|
| **目标** | 搭建 CodingKit 项目目录结构，配置 pyproject.toml、初始化 Git 仓库 |
| **涉及文件** | `pyproject.toml`, `setup.cfg`, `MANIFEST.in`, `.gitignore`, `README.md`, `src/codingkit/__init__.py`, `src/codingkit/__version__.py`, `src/codingkit/cli/__init__.py`, `src/codingkit/core/__init__.py`, `src/codingkit/tools/__init__.py`, `src/codingkit/governance/__init__.py`, `src/codingkit/feedback/__init__.py`, `src/codingkit/memory/__init__.py`, `src/codingkit/web/__init__.py`, `tests/__init__.py` |
| **实现要点** | ① 创建 `src/codingkit/` 包结构 ② 配置 `pyproject.toml`，依赖分组如下： - **核心 (core)**：`typer`, `pydantic`, `httpx`, `loguru`, `keyring`, `cryptography` - **可选 (llm)**：`anthropic`, `openai` - **可选 (memory)**：`chromadb` - **可选 (web)**：`fastapi`, `uvicorn` - **开发 (dev)**：`pytest`, `pytest-cov` ③ `[project.scripts]` 入口点：`codingkit = codingkit.cli.main:app` ④ 配置 `.gitignore`（排除 `__pycache__`, `.env`, `credentials.enc`, `*.egg-info`） ⑤ 配置 `pytest.ini` 或 `pyproject.toml` 中的 pytest 配置 |
| **验证步骤** | ① `pip install -e .` 安装成功 ② `python -c "import codingkit; print(codingkit.__version__)"` 成功 ③ `pytest tests/` 运行（无测试，但框架不报错） |
| **状态** | ✅ **已完成** (commit `1a988cc`) — 冷启动 agent 自主完成 |

**依赖**: 无  
**可并行**: 否  
**预估时间**: 5 分钟

---

### T1.2 凭据存储

| 字段 | 内容 |
|------|------|
| **目标** | 实现 `CredentialStore` 接口 + `KeychainStore` + `EncryptedFileStore` |
| **涉及文件** | `src/codingkit/core/credential_store.py`, `tests/test_credential_store.py` |
| **实现要点** | ① 定义 `CredentialStore` 抽象基类（`set`, `get`, `delete`, `exists`） ② 实现 `KeychainStore`（使用 `keyring` 库，服务名 `codingkit`） ③ 实现 `EncryptedFileStore`（AES-256-GCM，文件路径 `~/.codingkit/credentials.enc`，主密码由用户输入，使用 `cryptography` 库） ④ 实现 `get_credential_store(method: str)` 工厂函数 ⑤ 错误处理：钥匙串不可用时降级提示 |
| **验证步骤** | **失败测试**：① 构造 `KeychainStore`，写入后读取，断言值一致 ② 构造 `EncryptedFileStore`，写入后读取，断言值一致 ③ 写入后删除，断言 `exists()` 返回 False |
| **状态** | ✅ **已完成** (commit `1a988cc`) — 冷启动 agent 自主完成 |

**依赖**: T1.1  
**可并行**: 否  
**预估时间**: 5 分钟

---

### T1.3 LLM 抽象层

| 字段 | 内容 |
|------|------|
| **目标** | 实现 `LLMClient` 接口 + `ClaudeClient` + `OpenAIClient` + `MockLLMClient` |
| **涉及文件** | `src/codingkit/core/llm_client.py`, `src/codingkit/core/llm_factory.py`, `tests/test_llm_client.py` |
| **实现要点** | ① 定义 `LLMClient` 抽象基类（`generate(messages, tools)` → `LLMResponse`） ② 定义 `LLMResponse` 数据类（含 `content: str`, `tool_calls: List[ToolCall]`, `model: str`, `usage: dict`） ③ 定义 `ToolCall` 数据类（`name: str`, `arguments: dict`） ④ 实现 `ClaudeClient`（调用 anthropic SDK，支持 tool use） ⑤ 实现 `OpenAIClient`（调用 openai SDK，支持 function calling） ⑥ 实现 `MockLLMClient`（从预定义的响应列表中按顺序返回，用于单元测试） ⑦ 实现 `create_llm_client(model: str, api_key: str)` 工厂函数 |
| **验证步骤** | **失败测试**：① 构造 `MockLLMClient` 并注入预定义响应，断言按顺序返回 ② 构造 `MockLLMClient` 空响应列表，断言返回空 ③ 工厂函数传入无效模型名，断言抛出 ValueError |
| **状态** | ✅ **已完成** (commit `1a988cc`) — 冷启动 agent 自主完成 |

**依赖**: T1.1  
**可并行**: 否  
**预估时间**: 5 分钟

---

## Layer 2：Core（核心层）

### T2.1 工具实现

| 字段 | 内容 |
|------|------|
| **目标** | 实现 10 个工具的统一接口与具体实现 |
| **涉及文件** | `src/codingkit/tools/base.py`, `src/codingkit/tools/read_file.py`, `src/codingkit/tools/write_file.py`, `src/codingkit/tools/edit_file.py`, `src/codingkit/tools/execute_command.py`, `src/codingkit/tools/run_tests.py`, `src/codingkit/tools/search_files.py`, `src/codingkit/tools/search_content.py`, `src/codingkit/tools/install_dependencies.py`, `src/codingkit/tools/delete_file.py`, `src/codingkit/tools/git_operation.py`, `src/codingkit/tools/registry.py`, `tests/test_tools.py` |
| **实现要点** | ① 定义 `Tool` 抽象基类（`name`, `description`, `parameters`, `risk_level`, `execute(params)`） ② 定义 `RiskLevel` 枚举（`NORMAL`, `DANGEROUS`） ③ 定义 `ToolResult` 数据类（`success: bool`, `output: str`, `error: str | None`） ④ 实现 10 个工具类，每个标注 risk_level ⑤ 实现 `ToolRegistry`（注册所有工具，按名称查找） ⑥ 危险工具：`execute_command`, `install_dependencies`, `delete_file`, `git_operation` 实现时不做拦截，拦截由治理护栏负责 |
| **验证步骤** | **失败测试**：① 注册所有工具，断言按名称查找返回正确实例 ② 调用 `read_file` 读取存在的文件，断言返回内容 ③ 调用 `read_file` 读取不存在的文件，断言返回错误 ④ 调用 `write_file` 写入后读取，断言内容一致 ⑤ 调用 `run_tests` 对已知测试文件，断言返回结构化结果 ⑥ 查找不存在的工具名，断言返回 None |
| **状态** | ✅ **已完成** (commit `1a988cc`) — 冷启动 agent 自主完成 |

**依赖**: T1.1  
**可并行**: T2.2, T2.3  
**预估时间**: 8 分钟

---

### T2.2 治理护栏

| 字段 | 内容 |
|------|------|
| **目标** | 实现危险动作检测 + HITL 审批状态机 |
| **涉及文件** | `src/codingkit/governance/guardrail.py`, `src/codingkit/governance/approval.py`, `tests/test_guardrail.py` |
| **实现要点** | ① 实现 `Guardrail` 类：`check(action: ToolCall)` → `GuardrailResult` ② 定义 `GuardrailResult` 数据类（`is_dangerous: bool`, `risk_reason: str`, `suggested_safe_alternative: str | None`） ③ 危险动作规则：匹配工具名称（4 个危险工具）+ 参数模式（如 `rm -rf /`, `sudo` 等关键词） ④ 实现 `ApprovalHandler` 类：`request_approval(action)` → `ApprovalDecision`（y/n/m） ⑤ 定义 `ApprovalDecision` 枚举（`APPROVED`, `REJECTED`, `MODIFIED`） ⑥ `MODIFIED` 时返回用户修改后的参数 ⑦ 审批超时（默认 120 秒）→ 自动否决 |
| **验证步骤** | **失败测试**：① 传入危险命令 `Action(command="rm -rf /")` → 断言 `is_dangerous=True` ② 传入普通命令 `Action(command="ls -la")` → 断言 `is_dangerous=False` ③ 传入危险工具 `Action(name="delete_file", params={"path": "/etc"})` → 断言 `is_dangerous=True` ④ Mock 用户输入 `y` → 断言 `ApprovalDecision.APPROVED` ⑤ Mock 用户输入 `n` → 断言 `ApprovalDecision.REJECTED` ⑥ Mock 用户输入 `m` + 修改内容 → 断言 `ApprovalDecision.MODIFIED` 且返回修改后的参数 |
| **状态** | ✅ **已完成** (commit `69bf37e`) — subagent 在独立 worktree 中 TDD 实现，23 个测试通过 |

**依赖**: T1.1  
**可并行**: T2.1, T2.3  
**预估时间**: 5 分钟

---

### T2.3 记忆管理

| 字段 | 内容 |
|------|------|
| **目标** | 实现会话内记忆（内存）+ 跨会话记忆（ChromaDB）+ JSON 降级 |
| **涉及文件** | `src/codingkit/memory/memory_manager.py`, `src/codingkit/memory/vector_store.py`, `src/codingkit/memory/session_store.py`, `tests/test_memory.py` |
| **实现要点** | ① 实现 `SessionStore`（JSON 文件存储，保存/加载/列表/删除会话） ② 实现 `VectorStore`（ChromaDB 封装，`store(key, content, metadata)` / `search(query, n_results)`） ③ 实现 `MemoryManager` 统一接口：`remember(key, content, metadata)` / `recall(query)` / `clear()` ④ 向量数据库初始化失败时降级到内存存储（`InMemoryStore`） ⑤ 仅存储关键决策（修正策略选择、用户指令、重要约定），不存储全部对话 |
| **验证步骤** | **失败测试**：① 存储一条记录后搜索，断言返回相关结果 ② 存储多条记录，搜索相关性最高的，断言排序正确 ③ 清空后搜索，断言返回空列表 ④ 向量数据库不可用时，断言自动降级到内存存储 |

**依赖**: T1.1  
**可并行**: T2.1, T2.2  
**预估时间**: 5 分钟  
**状态**: ✅ **已完成** (commit `dfabba3`) — subagent 在独立 worktree 中 TDD 实现，27 个测试通过

---

## Layer 3：Feedback Loop（反馈闭环层 — 主攻方向）

### T3.1 校验器

| 字段 | 内容 |
|------|------|
| **目标** | 实现测试结果校验器，解析 pytest 的 JSON/JUnit XML 输出 |
| **涉及文件** | `src/codingkit/feedback/validator.py`, `tests/test_validator.py` |
| **实现要点** | ① 定义 `TestResult` 数据类（`total`, `passed`, `failed`, `errors`, `failures: List[FailureDetail]`, `raw_output`） ② 定义 `FailureDetail` 数据类（`test_name`, `error_type`, `error_message`, `traceback`） ③ 实现 `pytest 的 --json-report` 输出解析 ④ 实现 `pytest 的 --junitxml` 输出解析（作为 fallback） ⑤ 结果为空/超时/异常等边界处理 |
| **验证步骤** | **失败测试**：① 传入构造的 pytest JSON 输出 → 断言 `TestResult` 字段正确 ② 传入全部通过的测试结果 → 断言 `failed=0` ③ 传入部分失败的测试结果 → 断言 `failed>0` 且 `failures` 列表正确 ④ 传入空输出 → 断言标记为"未知错误" |
| **状态** | ✅ **已完成** (commit `9574d44`) — TDD 实现，JUnit XML 解析 + 原始输出回退，24 个测试通过 |

**依赖**: T2.1（需要 `run_tests` 工具支持）  
**可并行**: 否  
**预估时间**: 5 分钟

---

### T3.2 失败分类器

| 字段 | 内容 |
|------|------|
| **目标** | 实现基于规则引擎的失败分类器，支持 8 种分类 |
| **涉及文件** | `src/codingkit/feedback/classifier.py`, `tests/test_classifier.py` |
| **实现要点** | ① 定义 `FailureCategory` 枚举（8 种类型 + `UNCLASSIFIED`） ② 定义 `ClassificationResult` 数据类（`category: FailureCategory`, `confidence: float`, `summary: str`, `key_info: str`） ③ 实现规则引擎：每个分类对应一组关键词模式 + 优先级 ④ 分类优先级：编译错误 > 类型错误 > import 错误 > 边界条件 > 断言失败 > 死循环 > 超时 > 环境问题 ⑤ 无法匹配时返回 `UNCLASSIFIED` ⑥ 置信度计算：匹配到的关键词数量 / 总关键词数量 |
| **验证步骤** | **失败测试**：① 传入 `"SyntaxError: invalid syntax"` → 断言 `category == COMPILE_ERROR` ② 传入 `"AssertionError: expected 5, got 4"` → 断言 `category == ASSERTION_ERROR` ③ 传入 `"ModuleNotFoundError: No module named 'numpy'"` → 断言 `category == ENVIRONMENT_ERROR` ④ 传入 `"IndexError: list index out of range"` → 断言 `category == BOUNDARY_ERROR` ⑤ 传入 8 种分类各一条，断言全部正确分类 ⑥ 传入无法分类的错误 → 断言 `category == UNCLASSIFIED` |
| **状态** | ✅ **已完成** (commit `1293af3`) — TDD 实现，规则引擎 + 8 分类优先级 + 置信度计算，34 个测试通过 |

**依赖**: T3.1  
**可并行**: 否  
**预估时间**: 5 分钟

---

### T3.3 修正策略引擎（主攻方向 — 做深）

| 字段 | 内容 |
|------|------|
| **目标** | 实现修正策略状态机：状态管理、策略链、自动切换、阈值上报 |
| **涉及文件** | `src/codingkit/feedback/strategy_engine.py`, `src/codingkit/feedback/correction_state.py`, `tests/test_strategy_engine.py` |
| **实现要点** | ① 定义 `CorrectionState` 枚举（`ATTEMPTING`, `STRATEGY_EXHAUSTED`, `MAX_RETRIES_REACHED`, `USER_INTERVENTION`, `SUCCEEDED`, `CANCELLED`） ② 定义 `CorrectionContext` 数据类（`session_id`, `turn_id`, `attempt_number`, `current_strategy_index`, `strategy_chain: List[str]`, `history: List[CorrectionAttempt]`, `classification: FailureClassification`） ③ 定义 `CorrectionAttempt` 数据类（`strategy: str`, `result: str`, `success: bool`, `timestamp`） ④ 定义每种失败分类的策略链（见 SPEC §3.3.3） ⑤ 实现状态机核心逻辑： - `next_strategy(context)` → 返回下一个策略或上报信号 - 同一策略连续失败 3 次 → 自动切换到下一策略 - 总失败次数 ≥ 6 次 → 返回 `MAX_RETRIES_REACHED` - 所有策略用尽 → 返回 `STRATEGY_EXHAUSTED` ⑥ 状态机可观测：每次状态变化返回完整上下文（`CorrectionContext`） ⑦ 支持中断恢复：`resume(context)` 从上次状态继续 |
| **验证步骤** | **失败测试**：① 构造上下文，注入 3 次同一策略失败 → 断言 `current_strategy_index` 增加 ② 构造上下文，注入 6 次总失败 → 断言状态为 `MAX_RETRIES_REACHED` ③ 构造上下文，所有策略用尽 → 断言状态为 `STRATEGY_EXHAUSTED` ④ 注入成功结果 → 断言状态为 `SUCCEEDED` ⑤ 中断后恢复 → 断言从上次索引继续 ⑥ 对每种失败分类，断言策略链不为空 |
| **状态** | ✅ **已完成** (commit `8349222`) — TDD 实现，42 个测试通过，含状态机、策略链、自动切换、阈值上报、中断恢复 |

**依赖**: T3.2  
**可并行**: 否  
**预估时间**: 8 分钟（此 task 为重点，需要精细实现）

---

### T3.4 回灌器

| 字段 | 内容 |
|------|------|
| **目标** | 将修正历史组织为结构化上下文，注入 LLM 调用 |
| **涉及文件** | `src/codingkit/feedback/ingester.py`, `tests/test_ingester.py` |
| **实现要点** | ① 定义 `FeedbackContext` 数据类（`original_code`, `test_results`, `classification`, `correction_history`, `current_strategy`, `user_input`） ② 实现 `build_feedback_prompt(context)` → 生成结构化提示文本 ③ 提示模板包含：原始代码 → 失败信息 → 分类结果 → 已尝试策略 → 各策略结果 → 应尝试的下一策略 ④ 历史过长时自动截断：保留最近的 N 轮 ⑤ 回灌消息格式化为 LLM 能理解的结构（Markdown 或 JSON） |
| **验证步骤** | **失败测试**：① 传入完整修正历史 → 断言输出包含所有关键信息 ② 传入空历史 → 断言输出基本结构仍存在 ③ 历史过长触发截断 → 断言输出长度在限制内 ④ 输出格式为可解析的结构化文本 |
| **状态** | ✅ **已完成** (commit `9da2ddb`) — TDD 实现，16 个测试通过，含完整历史/空历史/截断/状态处理 |

**依赖**: T3.3  
**可并行**: 否  
**预估时间**: 5 分钟

---

## Layer 4：Agent Loop（主循环层）

### T4.1 Agent 主循环

| 字段 | 内容 |
|------|------|
| **目标** | 实现完整的 agent 主循环：组织上下文 → 调 LLM → 解析动作 → 分发执行 → 回灌结果 → 停机判断 |
| **涉及文件** | `src/codingkit/core/agent_loop.py`, `src/codingkit/core/context_builder.py`, `src/codingkit/core/response_parser.py`, `tests/test_agent_loop.py` |
| **实现要点** | ① 实现 `ContextBuilder`：收集项目文件、记忆、会话历史、工具定义，组装为 LLM 消息 ② 实现 `ResponseParser`：解析 LLM 响应，提取文本回复或工具调用 ③ 实现 `AgentLoop` 主类： - `run(task)` → 启动主循环 - `step()` → 单步执行（用于测试） - `cancel()` → 中断并保存状态 - `resume()` → 恢复中断的会话 ④ 主循环流程： build_context → call_llm → parse_response → if text: output → if tool: guardrail → execute → if test: feedback → repeat ⑤ 停机条件：用户明确完成 / 用户中断 / 达到最大轮次（安全阀） ⑥ 每一步都记录到 SessionStore |
| **验证步骤** | **失败测试**：① 使用 `MockLLMClient` 注入预定义响应 → 断言主循环按预期执行 ② 注入工具调用响应 → 断言工具被调用 ③ 注入文本回复 → 断言输出给用户 ④ 调用 `cancel()` → 断言状态保存 ⑤ 调用 `resume()` → 断言从上次状态继续 |
| **状态** | ✅ **已完成** (commit `fa7b068`) — 28 个测试通过，含 ContextBuilder、ResponseParser、AgentLoop 完整实现 |

**依赖**: T1.3, T2.1, T2.2, T2.3, T3.4  
**可并行**: 否  
**预估时间**: 10 分钟

---

### T4.2 CLI 实现

| 字段 | 内容 |
|------|------|
| **目标** | 实现所有 18 条 CLI 命令 |
| **涉及文件** | `src/codingkit/cli/main.py`, `src/codingkit/cli/commands/run.py`, `src/codingkit/cli/commands/config.py`, `src/codingkit/cli/commands/session.py`, `src/codingkit/cli/commands/tool.py`, `src/codingkit/cli/commands/web.py`, `tests/test_cli.py` |
| **实现要点** | ① 使用 Typer 框架实现 CLI 入口 ② 实现 `run` 命令（调用 AgentLoop） ③ 实现 `config` 命令组（key set/show/delete, method, model list/set） ④ 实现 `session` 命令组（list/show/delete） ⑤ 实现 `tool` 命令组（list/enable/disable） ⑥ 实现 `web` 命令（启动 FastAPI） ⑦ 实现 `init`, `status`, `cancel`, `version` 命令 ⑧ 所有命令提供清晰的帮助信息 |
| **验证步骤** | **失败测试**：① `codingkit --help` 输出所有命令 ② `codingkit version` 输出版本号 ③ 各命令无效参数 → 输出友好错误提示 |
| **状态** | ✅ **已完成** (commit `52250ed`) — 26 个测试通过，所有 18 条命令实现 |

**依赖**: T4.1, T1.2  
**可并行**: 否  
**预估时间**: 8 分钟

---

### T4.3 会话管理

| 字段 | 内容 |
|------|------|
| **目标** | 实现会话的持久化、列表、查看、删除、恢复 |
| **涉及文件** | `src/codingkit/core/session_manager.py`, `tests/test_session_manager.py` |
| **实现要点** | ① 实现 `SessionManager` 类的 CRUD 操作 ② 会话持久化到 JSON 文件（`~/.codingkit/sessions/`） ③ 中断时自动保存当前状态 ④ 恢复时重建 `AgentLoop` 上下文 |
| **验证步骤** | **失败测试**：① 创建会话 → 断言文件存在 ② 列出会话 → 断言包含刚创建的会话 ③ 删除会话 → 断言文件不存在 ④ 中断后恢复 → 断言上下文正确 |
| **状态** | ✅ **已完成** (commit `4e0ad5f`) — 17 个测试通过，含 CRUD、save/restore、中断保存 |

**依赖**: T4.1  
**可并行**: 否  
**预估时间**: 5 分钟

---

## Layer 5：WebUI

### T5.1 FastAPI 后端

| 字段 | 内容 |
|------|------|
| **目标** | 实现 WebUI 的 FastAPI 后端，提供 REST API + WebSocket |
| **涉及文件** | `src/codingkit/web/server.py`, `src/codingkit/web/routes.py`, `src/codingkit/web/websocket.py`, `src/codingkit/web/models.py`, `tests/test_web.py` |
| **实现要点** | ① FastAPI 应用初始化，CORS 配置 ② REST API：`POST /api/run`（提交任务）, `GET /api/status`（当前状态）, `GET /api/sessions`（会话列表）, `GET /api/sessions/{id}`（会话详情）, `POST /api/approve`（审批） ③ WebSocket：`/ws/status`（实时推送运行状态） ④ 静态文件服务（React 构建产物） ⑤ 与 AgentLoop 集成（通过异步调用） |
| **验证步骤** | **失败测试**：① 启动服务器 → 断言 `/docs` 返回 Swagger ② `GET /api/status` 返回正确状态 ③ 无效路径 → 返回 404 |

**依赖**: T4.1  
**可并行**: T5.2  
**预估时间**: 5 分钟  
**状态**: ✅ **已完成** — 6 个文件，20 个 API 测试，308 全部通过

---

### T5.2 React 前端

| 字段 | 内容 |
|------|------|
| **目标** | 实现 WebUI 的 React 前端：看板页 + 交互页 + 历史页 |
| **涉及文件** | `webui/`（独立目录）, `webui/package.json`, `webui/src/App.tsx`, `webui/src/pages/Dashboard.tsx`, `webui/src/pages/Interactive.tsx`, `webui/src/pages/History.tsx`, `webui/src/components/` |
| **实现要点** | ① React 项目初始化（Vite + TypeScript） ② 看板页：实时显示任务状态、运行日志、修正历史状态机流程图 ③ 交互页：输入新任务、审批拦截请求（y/n/m 按钮） ④ 历史页：列表 + 详情 ⑤ WebSocket 连接接收实时推送 ⑥ 构建产物输出到 `webui/dist/`，由 FastAPI 静态服务 |
| **验证步骤** | ① `npm run build` 成功 ② 构建产物可被 FastAPI 正确服务 |

**依赖**: T5.1  
**可并行**: 否  
**预估时间**: 10 分钟  
**状态**: ✅ **已完成** — 10 个源文件，Vite + React + TypeScript，3 页面，WebSocket 实时推送

---

## Layer 6：Distribution（分发层）

### T6.1 Dockerfile

| 字段 | 内容 |
|------|------|
| **目标** | 编写 Dockerfile，支持多阶段构建 |
| **涉及文件** | `Dockerfile`, `.dockerignore` |
| **实现要点** | ① 基于 `python:3.11-slim` ② 安装系统依赖（chromadb 需要的 lib） ③ 复制项目文件并安装 ④ 暴露端口（WebUI 8080） ⑤ 入口点设为 `codingkit` 命令 ⑥ 多阶段构建（前端 node 构建层 + Python 运行时层） |
| **验证步骤** | ① `docker build -t codingkit .` 成功 ② `docker run codingkit --help` 输出帮助信息 |

**依赖**: T4.2, T5.2  
**可并行**: T6.2, T6.3  
**预估时间**: 3 分钟  
**状态**: ✅ **已完成** — 多阶段构建 Dockerfile + .dockerignore

---

### T6.2 PyPI 打包

| 字段 | 内容 |
|------|------|
| **目标** | 配置 pyproject.toml 确保 `pip install codingkit` 可用 |
| **涉及文件** | `pyproject.toml`, `setup.cfg`（如需要）, `MANIFEST.in` |
| **实现要点** | ① 配置 `[project.scripts]` 入口点：`codingkit = codingkit.cli.main:app` ② 配置依赖列表（分核心依赖和可选依赖） ③ `[project.optional-dependencies] web = ["fastapi", "uvicorn"]` ④ 配置版本号读取自 `__version__.py` |
| **验证步骤** | ① `pip install -e .` 成功 ② `codingkit --help` 可用 ③ `pip install .[web]` 安装 WebUI 依赖 |

**依赖**: T4.2  
**可并行**: T6.1, T6.3  
**预估时间**: 3 分钟  
**状态**: ✅ **已完成** — 添加 `[project.scripts]` 入口点 + `all` 可选依赖

---

### T6.3 GitHub Actions CI

| 字段 | 内容 |
|------|------|
| **目标** | 配置 CI，每次 push 自动运行测试 + 构建 Docker 镜像 |
| **涉及文件** | `.github/workflows/ci.yml` |
| **实现要点** | ① `unit-test` job：Setup Python → pip install → pytest ② `docker-build` job：若 push 到 main 则构建 Docker 镜像 ③ 测试报告上传（可选） |
| **验证步骤** | ① push 后 CI 自动触发 ② CI 运行全部测试 ③ CI 构建 Docker 镜像 |

**依赖**: T6.1, T6.2  
**可并行**: 否  
**预估时间**: 3 分钟  
**状态**: ✅ **已完成** — 3 个 job（unit-test / docker-build / lint）

---

## Layer 7：Testing & Demo（测试与演示层）

### T7.1 Mock LLM 单元测试

| 字段 | 内容 |
|------|------|
| **目标** | 编写覆盖核心机制的 Mock LLM 单元测试，确保不依赖网络与真实 LLM |
| **涉及文件** | `tests/test_guardrail.py`, `tests/test_classifier.py`, `tests/test_strategy_engine.py`, `tests/test_validator.py`, `tests/test_agent_loop.py`（补充测试） |
| **实现要点** | ① 覆盖治理护栏：3 个测试用例（危险/普通/修改后放行） ② 覆盖失败分类器：9 个测试用例（8 种分类 + 1 个未分类） ③ 覆盖修正策略引擎：6 个测试用例（策略切换/阈值上报/成功/中断恢复/策略用尽/每种分类策略链） ④ 覆盖校验器：4 个测试用例（正常/全通过/部分失败/空输出） ⑤ 覆盖 Agent 主循环：3 个测试用例（Mock 响应/工具调用/中断恢复） |
| **验证步骤** | ① `pytest tests/ -v` 全部通过 ② 不联网时测试仍全部通过 ③ 所有测试使用 `MockLLMClient`，不使用真实 LLM |

**依赖**: T3.3, T2.2, T3.1, T3.2, T4.1  
**可并行**: 否  
**预估时间**: 8 分钟  
**状态**: ✅ **已完成** — 5 个文件补充 18 个测试，326 总测试通过

---

### T7.2 机制演示

| 字段 | 内容 |
|------|------|
| **目标** | 提交三个确定性机制演示脚本，展示核心机制 |
| **涉及文件** | `demo/guardrail_demo.py`, `demo/feedback_demo.py`, `demo/strategy_engine_demo.py`, `demo/run_all_demo.sh` |
| **实现要点** | ① **治理护栏演示**：传入危险命令 `rm -rf /` → 断言拦截；传入普通命令 `ls` → 断言放行 ② **反馈闭环演示**：构造一个"断言失败"的测试结果 → 通过分类器分类 → 修正策略引擎决策 → 断言状态机走向"尝试修正" ③ **重点维度演示**：构造多轮修正历史 → 断言状态机在 3 次同策略失败后自动切换，6 次总失败后上报人工 ④ 三个演示均可独立运行，不依赖真实 LLM |
| **验证步骤** | ① `python demo/guardrail_demo.py` 输出预期结果 ② `python demo/feedback_demo.py` 输出预期结果 ③ `python demo/strategy_engine_demo.py` 输出预期结果 ④ `bash demo/run_all_demo.sh` 全部通过 |
| **状态** | ✅ **已完成** (commit `ce48f9d`) — 3 个独立演示脚本 + PowerShell/Bash 运行脚本，全通过 |

**依赖**: T7.1  
**可并行**: 否  
**预估时间**: 5 分钟

---

## 执行顺序总结

```
Phase A: 基础建设
  T1.1 → T1.2 → T1.3
         ↓
Phase B: 核心构建（可并行）
  T2.1 ──────────────────┐
  T2.2 ──────────────────┤
  T2.3 ──────────────────┤
         ↓               ↓
Phase C: 反馈闭环（串行）
  T3.1 → T3.2 → T3.3 → T3.4
         ↓
Phase D: 主循环 ✅
  T4.1 → T4.2 → T4.3
         ↓
Phase E: WebUI（可并行）
  T5.1 ─┐
  T5.2 ─┘
         ↓
Phase F: 分发（可并行）
  T6.1 ─┐
  T6.2 ─┤
  T6.3 ─┘
         ↓
Phase G: 测试与演示
  T7.1 → T7.2
```

**说明**: 每个 task 由独立的 subagent 在 git worktree 中完成，遵循 TDD 红–绿–重构流程。完成一个 task 后标记 PLAN.md 并附 commit hash。