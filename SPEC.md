# CodingKit — SPEC 设计文档

> **项目类型**: A · Coding Agent Harness  
> **主攻方向**: 反馈闭环（Feedback Loop），修正策略状态机做深  
> **版本**: v0.1（草案）

---

## 1. 问题陈述

### 1.1 要解决什么问题

当前编码智能体（如 Claude Code、Codex）在生成代码时，如果测试失败，通常有两种表现：
1. **简单重试**：将原始输出和错误信息再次喂给 LLM，期待它自己"想明白"——没有针对失败原因做差异化处理。
2. **黑箱修正**：修正过程对用户不可见，用户不知道它经历了什么、为什么换策略、为什么放弃。

CodingKit 要解决的核心问题是：**当 agent 生成的代码测试失败时，如何让修正过程有分类、有策略、可观测、可干预**，而不是盲目重试。

### 1.2 目标用户

- **开发者**：想用 AI 辅助编码，但希望看到并控制 agent 的"思考过程"，而不是让它全自动黑箱操作。
- **AI4SE 学习者**：想理解 agent 的反馈闭环和修正机制是如何工作的。
- **教学场景**：作为展示"agent 工程化"的示例项目。

### 1.3 为什么值得做

**Agent = LLM + Harness**。LLM 负责"想"，harness 负责"做"。CodingKit 聚焦的是 harness 中最关键的一环——**反馈闭环**：当 agent 做错了，它如何知道自己错了？如何知道错在哪里？如何决定怎么改？这不是提示词能解决的问题，是需要工程化设计的。

---

## 2. 用户故事

| # | 用户故事 | INVEST |
|---|---------|--------|
| 1 | 作为开发者，当 CodingKit 生成的代码测试失败时，它能**自动将失败分类**（编译错误 / 断言失败 / 超时 / 环境问题 / 类型错误 / import 错误 / 边界条件遗漏 / 死循环），并根据分类**选择不同的修正策略**，而不是简单重试。 | 独立、可协商、有价值、可估算、小巧、可测试 |
| 2 | 作为开发者，我想观察 CodingKit 的**修正过程状态机**：当前处于第几轮修正、用了什么策略、为什么换策略、何时达到阈值并上报给我——这样我能理解它"在想什么"，而不仅仅看到最终结果。 | 独立、可协商、有价值、可估算、小巧、可测试 |
| 3 | 作为开发者，我想让 CodingKit 在**普通操作自动放行、危险操作拦截确认、任务完成暂停汇报**的混合模式下工作，这样我既能防止意外破坏，又不需要每步都点头。 | 独立、可协商、有价值、可估算、小巧、可测试 |
| 4 | 作为开发者，当 CodingKit 的修正策略**连续失败达到设定阈值（6 次）**后，它会主动暂停并向我汇报失败历史和已尝试过的策略，由我决定是给新方向、还是放弃——而不是无限循环或偷偷放弃。 | 独立、可协商、有价值、可估算、小巧、可测试 |
| 5 | 作为开发者，我可以在 CodingKit 运行过程中**随时打断并输入新指令**，它会基于当前上下文和新指令继续工作，而不是从头开始。 | 独立、可协商、有价值、可估算、小巧、可测试 |
| 6 | 作为开发者，我想在全新机器上通过一条命令安装 CodingKit 并安全配置 API Key，且所有凭据存储在操作系统钥匙串或加密文件中，不会意外泄露到 Git 历史或日志中。 | 独立、可协商、有价值、可估算、小巧、可测试 |

---

## 3. 功能规约

### 3.1 CLI 入口模块

| 命令 | 功能 | 输入 | 输出 | 边界条件 | 错误处理 |
|------|------|------|------|---------|---------|
| `codingkit init` | 在当前目录初始化 CodingKit 项目 | 无 | 生成 `.codingkit/config.yaml` 等配置文件 | 目录已存在时提示覆盖 | 无权限写入时报错 |
| `codingkit run "任务描述"` | 运行一个任务 | 自然语言任务描述 | 实时输出运行日志，任务完成后输出报告 | 空任务描述 → 提示输入；任务过长 → 截断警告 | LLM 调用失败 → 重试 3 次后报错 |
| `codingkit run --plan-only "任务"` | 只生成计划，不执行 | 自然语言任务描述 | 输出计划步骤列表 | 同上 | 同上 |
| `codingkit web` | 启动 WebUI 服务 | `--port` 参数（默认 8080） | 终端输出访问地址，浏览器可打开 WebUI | 端口被占用 → 自动找下一个可用端口 | 启动失败 → 提示端口冲突 |
| `codingkit config key set` | 配置 API Key | 用户输入 Key（隐藏输入） | 提示"配置成功" | 空输入 → 重新提示；已有 Key → 提示覆盖 | 写入钥匙串/文件失败 → 报错 |
| `codingkit config key show` | 查看 Key 状态 | 无 | 显示"已配置"或"未配置"，不回显明文 | — | — |
| `codingkit config key delete` | 清除 Key | 确认提示 | 提示"已清除" | 无 Key 时提示"未配置" | 删除失败 → 报错 |
| `codingkit config method keychain/file` | 切换凭据存储方式 | 存储方式名称 | 提示"切换成功" | 不支持的存储方式 → 提示可选列表 | 切换失败 → 报错 |
| `codingkit config max-tokens <N>` | 设置 LLM 最大输出 token 数 | token 数量（整数） | 提示"已设置" | 值 < 1 → 提示错误 | 保存配置失败 → 报错 |
| `codingkit config model list` | 查看可用模型 | 无 | 列出 Anthropic 和 OpenAI 的可用模型列表 | — | 网络不通时显示缓存的模型列表 |
| `codingkit config model set <name>` | 切换默认模型 | 模型名称 | 提示"已设为默认" | 模型名称不存在 → 提示可选列表 | 保存配置失败 → 报错 |
| `codingkit session list` | 查看历史会话列表 | 无 | 显示会话 ID、创建时间、状态、任务摘要 | 无会话时提示"暂无记录" | — |
| `codingkit session show <id>` | 查看会话详情 | 会话 ID | 显示完整会话记录（任务、轮次、工具调用、修正历史） | ID 不存在 → 提示"未找到" | — |
| `codingkit session delete <id>` | 删除会话 | 会话 ID | 确认提示后删除 | 同上 | 删除失败 → 报错 |
| `codingkit tool list` | 查看所有可用工具及状态 | 无 | 列出工具名称、状态（启用/禁用）、是否为危险动作 | — | — |
| `codingkit tool enable <name>` | 启用某个工具 | 工具名称 | 提示"已启用" | 名称不存在 → 提示可选列表 | — |
| `codingkit tool disable <name>` | 禁用某个工具 | 工具名称 | 提示"已禁用" | 同上 | — |
| `codingkit status` | 查看当前运行状态 | 无 | 显示当前任务、进度、当前轮次 | 无运行中任务 → 提示"空闲" | — |
| `codingkit cancel` | 取消当前任务 | 确认提示 | 任务被中断，状态保存可恢复 | 无运行中任务 → 提示"无任务" | — |
| `codingkit version` | 查看版本 | 无 | 输出版本号 | — | — |

### 3.2 Agent 主循环模块

**输入**: 用户任务描述 + 当前上下文（项目文件、会话历史、记忆）

**行为**:
1. 组织上下文 → 调用 LLM → 解析响应
2. 若响应为文本回复 → 输出给用户，继续下一轮
3. 若响应为工具调用 → 经治理护栏判断 → 执行或拦截 → 将结果回灌 → 继续下一轮
4. 若任务完成 → 生成报告 → 暂停 → 等待用户决定下一步
5. 若用户中断 → 保存当前状态 → 退出

**输出**: 实时日志 + 最终任务报告

**边界条件**:
- LLM 返回格式无法解析 → 重试 3 次，每次附带格式示例
- 连续 3 次解析失败 → 暂停并上报用户
- 上下文超出模型 token 限制 → 自动截断最旧的历史

**错误处理**:
- LLM API 调用失败（网络/鉴权/限流）→ 重试 3 次，指数退避
- 所有重试用尽 → 暂停并上报用户

### 3.3 反馈闭环模块（主攻方向）

#### 3.3.1 校验器

**输入**: 测试运行的原始输出（stdout/stderr）

**行为**:
- 解析 pytest 的 JSON/JUnit XML 输出
- 提取：总用例数、通过数、失败数、错误数、每个失败用例的名称与错误信息
- 将非结构化输出转化为结构化 `TestResult` 对象

**输出**: `TestResult` 结构化数据

**边界条件**:
- 测试输出为空 → 标记为"未知错误"
- 测试框架不存在 → 标记为"环境问题"
- 测试超时 → 标记为"超时"

#### 3.3.2 失败分类器

**输入**: `TestResult` 结构化数据

**行为**:
- 根据错误信息的关键词和模式，将失败分类为 8 种类型：

| 分类 | 判断依据 | 示例错误信息 |
|------|---------|-------------|
| 编译错误 | SyntaxError、IndentationError、NameError | `SyntaxError: invalid syntax` |
| 断言失败 | AssertionError、assert 语句 | `AssertionError: expected 5, got 4` |
| 超时 | 超时信号、timeout 标志 | `TimeoutError: test timed out after 30s` |
| 环境问题 | ModuleNotFoundError、ImportError | `ModuleNotFoundError: No module named 'numpy'` |
| 类型错误 | TypeError、TypeError 子类 | `TypeError: unsupported operand type(s)` |
| Import 错误 | ImportError（非 ModuleNotFoundError 子类） | `ImportError: cannot import name 'X'` |
| 边界条件遗漏 | IndexError、KeyError、ValueError | `IndexError: list index out of range` |
| 死循环/资源耗尽 | MemoryError、RecursionError、OOM | `RecursionError: maximum recursion depth exceeded` |

**输出**: 失败分类结果（分类标签 + 置信度 + 关键信息摘要）

**边界条件**:
- 无法匹配任何已知模式 → 标记为"未分类"，走通用修正策略
- 多个分类同时匹配 → 按优先级取最高者

#### 3.3.3 修正策略引擎（主攻深度的维度）

**输入**: 失败分类结果 + 修正历史（已尝试过的策略）

**行为**:
- 基于状态机管理修正过程：

```
                    ┌──────────────┐
                    │  收到失败结果  │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐
                    │  分类失败类型  │
                    └──────┬───────┘
                           ▼
                    ┌──────────────┐     ┌─────────────────┐
                    │  选择修正策略  │────→│ 尝试 + 记录结果  │
                    └──────────────┘     └────────┬────────┘
                                                  │
                                    ┌─────────────┴─────────────┐
                                    ▼                           ▼
                            ┌────────────────┐         ┌────────────────┐
                            │  成功 → 完成    │         │  再次失败       │
                            └────────────────┘         └────────┬───────┘
                                                                 ▼
                            ┌──────────────────────────────────────────┐
                            │  策略是否切换？                           │
                            │  ├─ 同策略失败 < 3 次 → 继续尝试          │
                            │  ├─ 同策略失败 ≥ 3 次 → 切换到下一策略    │
                            │  └─ 总失败次数 ≥ 6 次 → 上报人工          │
                            └──────────────────────────────────────────┘
```

- 每种失败分类对应的策略链：

| 失败分类 | 策略链（按顺序） |
|---------|----------------|
| 编译错误 | ① 提示 LLM 检查语法 → ② 提示 LLM 检查代码结构 → ③ 上报人工 |
| 断言失败 | ① 提示 LLM 比较预期值与实际值 → ② 提示 LLM 检查逻辑 → ③ 上报人工 |
| 超时 | ① 提示 LLM 优化算法 → ② 提示 LLM 减少循环/数据量 → ③ 上报人工 |
| 环境问题 | ① 自动安装缺失依赖 → ② 提示 LLM 检查依赖声明 → ③ 上报人工 |
| 类型错误 | ① 提示 LLM 检查类型标注 → ② 提示 LLM 检查类型转换 → ③ 上报人工 |
| Import 错误 | ① 检查导入路径 → ② 提示 LLM 确认文件名 → ③ 上报人工 |
| 边界条件遗漏 | ① 提示 LLM 检查边界条件 → ② 提示 LLM 检查空值处理 → ③ 上报人工 |
| 死循环/资源耗尽 | ① 提示 LLM 检查终止条件 → ② 提示 LLM 优化递归/循环 → ③ 上报人工 |
| 未分类 | ① 通用修正 → ② 上报人工 |

**输出**: 修正策略决策（策略名称 + 状态机状态 + 历史记录）

**边界条件**:
- 达到最大重试次数（6 次）→ 暂停上报人工
- 用户中断修正 → 保存当前状态，允许后续恢复
- 同一个策略连续失败 3 次 → 自动切换到下一策略

#### 3.3.4 回灌器

**输入**: 修正历史 + 当前测试结果

**行为**:
- 将修正历史组织成结构化上下文，追加到 LLM 的对话窗口
- 包含：原始代码、失败信息、分类结果、已尝试策略、各策略结果、应尝试的下一策略

**输出**: 结构化回灌消息

**边界条件**:
- 上下文过长 → 截断最旧的修正历史，保留最近的 N 轮

### 3.4 工具分发模块

**工具列表**:

| 工具 | 名称 | 输入 | 输出 | 危险等级 |
|------|------|------|------|---------|
| 读文件 | `read_file` | 文件路径 | 文件内容 | 普通 |
| 写文件 | `write_file` | 文件路径 + 内容 | 写入结果 | 普通 |
| 编辑文件 | `edit_file` | 文件路径 + 旧内容 + 新内容 | 替换结果 | 普通 |
| 执行 Shell 命令 | `execute_command` | 命令字符串 | stdout + stderr + 返回值 | **危险** |
| 运行测试 | `run_tests` | 测试路径（可选） | 结构化测试结果 | 普通 |
| 搜索文件 | `search_files` | 文件名/模式 | 匹配文件列表 | 普通 |
| 搜索内容 | `search_content` | 关键词 + 路径（可选） | 匹配行列表 | 普通 |
| 安装依赖 | `install_dependencies` | 包名列表 | 安装结果 | **危险** |
| 删除文件 | `delete_file` | 文件路径 | 删除结果 | **危险** |
| Git 操作 | `git_operation` | 操作类型 + 参数 | 操作结果 | **危险** |

**行为**:
- 接收到 LLM 的工具调用请求
- 校验工具名称是否存在
- 校验参数是否完整
- 判断危险等级 → 普通则自动执行，危险则交治理护栏
- 执行工具并返回结果

### 3.5 治理护栏模块

**输入**: 工具调用请求

**行为**:
- 匹配危险动作规则
- 危险动作 → 暂停 → 显示动作详情 → 用户选择：
  - `y`：放行
  - `n`：否决，返回给 LLM "该操作被用户拒绝"
  - `m`：修改后放行，用户输入修改后的命令
- 记录审批日志

**输出**: 执行结果（放行后）或拒绝信息

**边界条件**:
- 用户长时间不响应 → 超时后自动否决（可配置超时时间）
- 危险动作参数包含明显恶意模式 → 即使放行也记录警告

### 3.6 记忆模块

**输入**: 需要存储的信息（对话历史、决策记录、项目上下文）

**行为**:
- 当前会话记忆：存储在内存中，按需组织
- 跨会话记忆：使用向量数据库（ChromaDB）存储关键决策和项目知识
- 按需检索：只将相关记忆注入 LLM 上下文，而非全量载入

**输出**: 按需检索到的相关记忆

**边界条件**:
- 向量数据库初始化失败 → 回退到内存 + JSON 文件
- 检索结果为空 → 返回空，不影响主流程

### 3.7 WebUI 模块

**行为**:
- 看板页：实时显示当前任务状态、运行日志、修正历史状态机
- 交互页：输入新任务、审批拦截请求（y/n/m）
- 历史页：回顾以往会话、查看修正过程

**技术选型**: FastAPI + React 前端

**边界条件**:
- WebSocket 断连 → 自动重连
- 多个 WebUI 实例指向同一后端 → 状态同步

---

## 4. 非功能性需求

### 4.1 性能

| 指标 | 目标 |
|------|------|
| 修正循环最大重试次数 | 6 次 |
| LLM API 调用超时 | 60 秒 |
| 工具执行超时（Shell 命令） | 300 秒 |
| WebUI 页面加载时间 | < 3 秒 |
| 向量数据库检索 | < 1 秒 |

### 4.2 安全（含凭据威胁模型）

**凭据威胁模型**:

| 威胁 | 描述 | 严重程度 | 对策 |
|------|------|---------|------|
| 凭据硬编码 | API Key 被写入源码 | 严重 | 凭据管理强制使用钥匙串或加密文件，代码中不存在明文 Key |
| 凭据泄露至 Git | Key 被提交到仓库 | 严重 | `.gitignore` 排除所有凭据文件；`pre-commit` 钩子检测 Key 模式 |
| 凭据泄露至日志 | Key 在日志或终端输出中回显 | 高 | 所有日志输出自动过滤 Key 模式；`show` 命令不回显明文 |
| 进程环境泄露 | 子进程通过环境变量读取 Key | 中 | Key 不通过环境变量传递；优先使用钥匙串 API |
| 未经授权的工具执行 | 危险操作被 LLM 调用 | 高 | 治理护栏拦截所有危险动作，必须人工确认 |
| 会话劫持 | WebUI 未授权访问 | 中 | WebUI 绑定 localhost，不开放公网 |

**凭据存储方案**:
- 策略模式：`CredentialStore` 接口
  - `KeychainStore`：操作系统钥匙串（macOS Keychain / Windows Credential Manager / Linux Secret Service）
  - `EncryptedFileStore`：AES-256 加密文件，主密码由用户输入
- 用户可通过 `codingkit config method` 切换

### 4.3 可用性

- 所有错误信息以人类可读的中文/英文展示
- 交互式命令提供清晰的提示和可选项
- 中断后可恢复：会话状态持久化保存
- 首次运行引导式配置：检测到无 Key 时自动进入配置流程

### 4.4 可观测性

- **控制台输出**：人类可读的彩色日志（info / warn / error 三级）
- **文件日志**：JSON 结构化日志，便于 WebUI 读取和后续分析
- **关键事件**：LLM 调用、工具执行、修正策略切换、拦截审批等事件均记录
- **修正过程**：状态机状态变化实时输出

---

## 5. 系统架构

### 5.1 组件图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         用户界面层                                   │
│  ┌──────────────────┐          ┌────────────────────────────────┐   │
│  │  CLI (Typer)      │          │  WebUI (FastAPI + React)      │   │
│  │  ├─ run/status    │          │  ├─ 看板页 (实时状态)          │   │
│  │  ├─ config/session│          │  ├─ 交互页 (任务/审批)         │   │
│  │  ├─ tool/version  │          │  └─ 历史页 (回顾)              │   │
│  │  └─ cancel        │          │                                │   │
│  └────────┬──────────┘          └──────────────┬─────────────────┘   │
└───────────┼────────────────────────────────────┼─────────────────────┘
            │                                    │
            ▼                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         应用层                                       │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                    Agent 主循环                               │    │
│  │  组织上下文 → 调 LLM → 解析动作 → 分发执行 → 回灌结果 → 停机  │    │
│  └──┬──────────┬──────────┬──────────┬──────────┬──────────────┘    │
│     │          │          │          │          │                    │
│     ▼          ▼          ▼          ▼          ▼                    │
│  ┌──────┐ ┌──────┐ ┌────────┐ ┌────────┐ ┌──────────┐             │
│  │ 工具  │ │ 治理  │ │ 反馈    │ │ 记忆    │ │ 上下文    │             │
│  │ 分发器 │ │ 护栏  │ │ 闭环    │ │ 管理器  │ │ 组装器   │             │
│  │      │ │      │ │        │ │        │ │          │             │
│  │ 10个 │ │ HITL │ │ 校验器 │ │ 内存   │ │ Prompt   │             │
│  │ 工具  │ │ 状态机│ │ 分类器 │ │ 向量库 │ │ 模板     │             │
│  │      │ │      │ │ 修正   │ │ JSON   │ │ Token    │             │
│  │      │ │      │ │ 策略   │ │ 文件   │ │ 计数器   │             │
│  └──────┘ └──────┘ └────────┘ └────────┘ └──────────┘             │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
            │          │                    │
            ▼          ▼                    ▼
┌──────────────┐ ┌──────────┐ ┌──────────────────────┐
│  外部依赖     │ │  LLM 层  │ │  持久化层             │
│  ┌────────┐  │ │ ┌──────┐ │ │  ┌──────────────┐   │
│  │ 文件系统│  │ │ │Claude│ │ │  │ ChromaDB     │   │
│  │ 操作系统│  │ │ │OpenAI│ │ │  │ (向量存储)    │   │
│  │ Shell   │  │ │ │Mock  │ │ │  ├──────────────┤   │
│  │ Git     │  │ │ └──────┘ │ │  │ JSON 文件     │   │
│  └────────┘  │ └──────────┘ │  │ (会话/配置)   │   │
│              │             │  │ │ 운영체제      │   │
└──────────────┘              │  │ │ 钥匙串        │   │
                              │  │ └──────────────┘   │
                              │  └────────────────────┘
```

### 5.2 数据流

```
用户输入任务
    │
    ▼
Agent 主循环
    │
    ├──→ 上下文组装器：收集项目文件 + 记忆 + 会话历史
    │       │
    │       ▼
    │   LLM 调用（Claude / OpenAI / Mock）
    │       │
    │       ▼
    │   响应解析器：提取文本回复或工具调用
    │       │
    │       ├──→ 文本回复 → 输出给用户
    │       │
    │       └──→ 工具调用 → 治理护栏
    │               │
    │               ├──→ 危险 → 用户审批（y/n/m）
    │               │       │
    │               │       ├──→ y/m → 执行工具
    │               │       └──→ n → 反馈给 LLM
    │               │
    │               └──→ 普通 → 执行工具
    │                       │
    │                       ├──→ 运行测试 → 反馈闭环
    │                       │       │
    │                       │       ├──→ 校验器解析
    │                       │       ├──→ 分类器分类
    │                       │       ├──→ 修正策略引擎
    │                       │       └──→ 回灌器 → 回 LLM
    │                       │
    │                       └──→ 其他工具 → 回灌给 LLM
    │
    └──→ 任务完成 → 生成报告 → 暂停 → 等待用户
```

### 5.3 外部依赖

**依赖分组**（对应 `pyproject.toml` 的 extras 组织）：

| 组 | 依赖 | 用途 | 说明 |
|-----|------|------|------|
| **核心 (core)** | `typer>=0.12` | CLI 框架 | 必选，`pip install codingkit` 即装 |
| | `pydantic>=2.0` | 数据模型校验 | 必选 |
| | `httpx>=0.27` | HTTP 客户端 | 必选 |
| | `loguru>=0.7` | 结构化日志 | 必选 |
| | `keyring>=24.0` | 操作系统钥匙串访问 | 必选（Linux 需 D-Bus） |
| | `cryptography>=41.0` | 加密文件加解密 | 必选 |
| **LLM (llm)** | `anthropic>=0.30` | Claude 模型调用 | 可选，`pip install codingkit[llm]` |
| | `openai>=1.0` | GPT 及 OpenAI 兼容 provider（DeepSeek / GLM / Kimi / MiniMax / Qwen）调用 | 可选，同上 |
| **记忆 (memory)** | `chromadb>=0.4` | 向量存储与检索 | 可选，`pip install codingkit[memory]`（降级到 JSON 文件） |
| **WebUI (web)** | `fastapi>=0.100` | WebUI 后端 | 可选，`pip install codingkit[web]` |
| | `uvicorn>=0.23` | ASGI 服务器 | 可选，同上 |
| **全部 (all)** | 以上所有 | — | `pip install codingkit[all]` |
| **开发 (dev)** | `pytest>=7.0` | 测试框架 | 开发依赖，`pip install codingkit[dev]` |
| | `pytest-cov` | 测试覆盖率 | 开发依赖 |

**依赖安装命令**:

```bash
pip install codingkit              # 核心（轻量）
pip install codingkit[llm]         # 加 LLM 支持
pip install codingkit[memory]      # 加向量记忆
pip install codingkit[web]         # 加 WebUI 支持
pip install codingkit[all]         # 全部装上
pip install codingkit[dev]         # 开发模式（含测试）
```

---

## 6. 数据模型

### 6.1 实体关系

```
Session (会话)
  ├── id: UUID (主键)
  ├── created_at: datetime
  ├── updated_at: datetime
  ├── status: enum (running / completed / cancelled / paused)
  ├── task_description: string
  ├── model: string (使用的模型名称)
  ├── turns: List[Turn] (交互轮次)
  └── summary: string (任务完成摘要)

Turn (交互轮次)
  ├── id: UUID (主键)
  ├── session_id: UUID (外键 → Session)
  ├── turn_number: int
  ├── llm_request: object (请求完整内容)
  ├── llm_response: object (响应完整内容)
  ├── parsed_action: Action (解析后的动作)
  ├── tool_result: object (工具执行结果)
  ├── approval: ApprovalRecord (审批记录, 如有)
  └── timestamp: datetime

Action (动作)
  ├── type: string (工具名称)
  ├── params: dict (工具参数)
  ├── risk_level: enum (normal / dangerous)
  └── status: enum (pending / approved / rejected / executed / failed)

ApprovalRecord (审批记录)
  ├── action_id: UUID (外键 → Action)
  ├── decision: enum (approved / rejected / modified)
  ├── modified_params: dict (如修改后放行)
  ├── user_input: string (用户输入内容)
  └── timestamp: datetime

TestResult (测试结果)
  ├── turn_id: UUID (外键 → Turn)
  ├── total: int
  ├── passed: int
  ├── failed: int
  ├── errors: int
  ├── failures: List[FailureDetail]
  └── raw_output: string

FailureDetail (失败详情)
  ├── test_name: string
  ├── error_type: string
  ├── error_message: string
  ├── classification: FailureClassification (分类结果)
  └── traceback: string

FailureClassification (失败分类)
  ├── category: enum (syntax_error / assertion_error / timeout /
  │                 environment_error / type_error / import_error /
  │                 boundary_error / resource_exhaustion / unclassified)
  ├── confidence: float (0.0-1.0)
  └── summary: string

CorrectionRecord (修正记录)
  ├── id: UUID (主键)
  ├── session_id: UUID (外键 → Session)
  ├── turn_id: UUID (外键 → Turn)
  ├── attempt_number: int
  ├── classification: FailureClassification
  ├── strategy: string (使用的修正策略)
  ├── strategy_chain: List[string] (策略链)
  ├── strategy_index: int (当前策略在链中的位置)
  ├── status: enum (pending / in_progress / succeeded / failed)
  ├── result: string (修正结果描述)
  └── timestamp: datetime

Config (配置)
  ├── id: string (主键, 固定为 "default")
  ├── default_model: string
  ├── credential_method: string (keychain / file)
  ├── max_retries: int (默认 6)
  ├── tool_enabled: dict (工具名称 → bool)
  └── updated_at: datetime
```

### 6.2 约束

- Session 的 `turns` 按 `turn_number` 顺序排列
- 一个 Session 最多有一条处于 `running` 状态的记录
- CorrectionRecord 的 `attempt_number` 不超过 `max_retries`（默认 6）
- Config 为单例模式，全局只有一份

---

## 7. 凭据与分发设计

### 7.1 凭据存储方案

**方案: 策略模式（Strategy Pattern）**

```
CredentialStore (接口)
  ├── set(key_name, value) → void
  ├── get(key_name) → string | None
  ├── delete(key_name) → void
  └── exists(key_name) → bool
    
KeychainStore (钥匙串实现)
  ├── 使用 keyring 库
  ├── 服务名: "codingkit"
  └── 平台: macOS Keychain / Windows CredMan / Linux Secret Service

EncryptedFileStore (加密文件实现)
  ├── 使用 cryptography 库 (AES-256-GCM)
  ├── 存储路径: ~/.codingkit/credentials.enc
  ├── 主密码: 首次运行时由用户输入
  └── 主密码不存储，仅用于加解密
```

**录入/更新/清除流程**:
- **首次运行**: 检测到无 Key → 引导用户输入 → 根据配置的 method 存储
- **更新**: `codingkit config key set` → 覆盖已有的 Key
- **清除**: `codingkit config key delete` → 确认后删除
- **查看状态**: `codingkit config key show` → 只显示"已配置/未配置"，不回显明文

### 7.2 分发形态

**形态 1: PyPI 包**
```
pip install codingkit
```
- 目标平台: Linux / macOS / Windows
- Python 3.11+
- 依赖自动安装

**形态 2: Docker 镜像**
```
docker pull codingkit/codingkit:latest
docker run -it codingkit/codingkit:latest
```
- 基于 Python 3.11-slim
- 内置所有依赖
- 用户需通过 `-v` 挂载项目目录和凭据目录

**Key 在目标机的安全配置方式**:
- 容器内: 通过 `-v ~/.codingkit:/root/.codingkit` 挂载凭据目录，或容器首次运行时交互式输入
- 原生安装: 使用钥匙串或 `~/.codingkit/credentials.enc` 加密文件

**已知限制**:
- PyPI 包: 需要系统安装 Python 3.11+；钥匙串功能在 Linux 需要 D-Bus
- Docker 镜像: 需要安装 Docker；容器内文件操作需挂载卷

---

## 8. 技术选型与理由

| 维度 | 选型 | 理由 |
|------|------|------|
| **语言** | Python 3.11+ | LLM 生态最丰富（anthropic/openai SDK）；pytest 输出结构化，便于校验器解析；开发效率高，省下的时间投入到"做深"修正策略 |
| **测试框架** | pytest | 支持 JSON/JUnit XML 输出，校验器可直接解析结构化数据；fixture/mock/参数化支持 TDD |
| **LLM SDK** | anthropic + openai | 双支持，用户可切换；抽象层统一接口，Mock 实现用于单元测试 |
| **CLI 框架** | Typer | 基于 Click，类型安全的参数解析，自动生成帮助信息 |
| **WebUI 后端** | FastAPI | 异步支持，WebSocket 用于实时推送，自动生成 OpenAPI 文档 |
| **WebUI 前端** | React | 组件化开发，状态管理清晰，生态成熟 |
| **向量数据库** | ChromaDB | 纯 Python 实现，无需额外服务，支持降级到 JSON 文件 |
| **凭据存储** | keyring + cryptography | 钥匙串优先，加密文件降级；策略模式统一接口 |
| **容器化** | Docker | 标准 OCI 镜像，支持多平台构建 |
| **包管理** | PyPI | Python 生态标准分发方式，pip 一键安装 |
| **CI** | GitHub Actions | 与 GitHub 仓库集成，自动运行测试和构建 |

---

## 9. 验收标准

| 功能 | 验收标准 |
|------|---------|
| CLI 命令 | 所有 18 条命令均可运行并返回预期输出 |
| Agent 主循环 | 能完成"接收任务 → 调用 LLM → 执行工具 → 输出结果"的完整闭环 |
| 反馈闭环 - 校验器 | 能解析 pytest 的 JSON 输出并提取结构化失败信息 |
| 反馈闭环 - 分类器 | 能正确分类 8 种失败类型，精度 ≥ 90%（Mock 测试） |
| 反馈闭环 - 修正策略 | 状态机正确运行，6 次失败后自动上报；同一策略 3 次失败后自动切换 |
| 反馈闭环 - 回灌器 | 修正历史正确组织为上下文，注入 LLM 调用 |
| 治理护栏 | 4 种危险动作全部拦截，支持 y/n/m 三种决策 |
| 记忆 | 跨会话检索返回相关结果 |
| 凭据安全 | Key 不硬编码、不提交 Git、不写入日志 |
| 中断恢复 | 中断后重新启动，会话状态恢复 |
| WebUI | 可正常访问，能输入任务、审批、查看历史 |
| Docker | `docker build` + `docker run` 可启动 |
| PyPI | `pip install` 后 `codingkit` 命令可用 |
| CI | 每次 push 自动运行测试，构建镜像 |
| Mock 测试 | 移除真实 LLM 后，核心机制仍可用单测验证 |

---

## 10. 风险与未决问题

### 10.1 已识别的风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| LLM 输出格式不稳定，解析动作失败 | 主循环卡住 | 中 | 重试 3 次 + 格式校验 + 容错解析；仍失败则上报人工 |
| 修正循环无限重试 | 浪费 token 和时间 | 低 | 最大重试次数 6 次 + 同策略 3 次切换 + 阈值后上报 |
| ChromaDB 增加项目复杂度 | 记忆部分可能成为瓶颈 | 中 | 精简向量库使用范围，只存关键决策；支持降级到 JSON 文件 |
| WebUI 开发时间不可控 | 拖累核心机制 | 中 | WebUI 用 React 简单模板，先出可用版；核心机制优先 |
| 跨平台钥匙串兼容性 | Linux 上 D-Bus 问题 | 中 | 加密文件作为 fallback；文档说明各平台前提 |
| 多 LLM 供应商抽象层维护 | 接口差异导致问题 | 低 | 统一接口 + 各供应商适配器模式 |

### 10.2 未决问题

| 问题 | 状态 | 计划 |
|------|------|------|
| 是否支持流式输出（LLM 逐 token 输出）？ | 待定 | 若时间允许则加入 |
| WebUI 是否需要用户认证？ | 待定 | 绑定 localhost 即可，无需认证 |
| 是否支持多语言测试框架（如 pytest + jest + go test）？ | 待定 | 优先支持 pytest，后续扩展 |
| 修正策略的"策略链"是否允许用户自定义？ | 待定 | 配置文件支持，但优先级低 |

---

## 11. 领域与机制设计（Coding Agent Harness 专用）

### 11.1 领域分析

Coding 领域（软件开发场景）的四个核心机制：

| 机制 | 领域中的形态 | CodingKit 的实现方式 |
|------|-------------|-------------------|
| **动作/工具** | 读写文件、执行命令、运行构建与测试 | 10 个工具，统一接口，危险等级标注 |
| **客观反馈信号** | 测试结果、lint 输出、类型检查结果 | 测试结果校验器，解析 pytest 结构化输出 |
| **危险动作** | 删除文件、执行危险命令、对外发布 | 治理护栏，规则匹配 + HITL 审批 |
| **记忆** | 项目约定、历史决策、代码库知识 | 向量数据库 + 会话历史，按需检索 |

### 11.2 重点维度：反馈闭环

**为什么选择反馈闭环作为深入方向**：

在 coding 场景中，反馈闭环是"harness 能否自我修正"的核心。一个没有反馈闭环的 harness 本质上只是"LLM + 工具"的简单封装——LLM 输出什么就执行什么，错了也不会知道。而反馈闭环让 harness 具备自我修正能力，这是 harness 区别于"LLM 包装器"的关键特征。

**反馈闭环的四层机制（全部由代码实现）**：

1. **校验器（Validator）** — 确定性代码
   - 解析 pytest 的 JSON/JUnit XML 输出
   - 提取结构化 TestResult
   - 不受 LLM 不确定性影响，可独立单元测试

2. **失败分类器（Failure Classifier）** — 确定性规则引擎
   - 基于关键词匹配和优先级规则
   - 输出 8 种分类标签
   - 可独立单元测试，无需 LLM

3. **修正策略引擎（Correction Strategy Engine）** — 状态机（重点深入）
   - 状态管理：尝试 → 失败 → 换策略 → 再试 → 上报
   - 每种失败类型有独立的策略链
   - 同策略 3 次失败自动切换
   - 总失败 6 次上报人工
   - 状态机可观测：每一步状态变化都记录和输出
   - 可独立单元测试，无需 LLM

4. **回灌器（Feedback Ingester）** — 确定性代码
   - 将修正历史组织为结构化上下文
   - 自动截断过长的历史
   - 可独立单元测试

### 11.3 判定标准验证

**移除真实 LLM 后，这些机制还能用单测验证吗？**

| 机制 | Mock LLM 下可测试？ | 测试方式 |
|------|-------------------|---------|
| 校验器 | ✅ | 传入构造的 pytest 输出，断言解析结果 |
| 分类器 | ✅ | 传入构造的错误信息，断言分类标签 |
| 修正策略引擎 | ✅ | 注入状态，断言状态转换和策略选择 |
| 回灌器 | ✅ | 传入修正历史，断言输出上下文结构 |
| 治理护栏 | ✅ | 传入构造的动作，断言拦截/放行结果 |
| 工具分发器 | ✅ | 传入工具调用，断言执行路径 |

**结论**: 所有核心机制在移除 LLM 后均可通过确定性单元测试验证，符合 §A.4-C 的硬标准。

### 11.4 机制演示计划

按 §A.6 要求，提交以下三个确定性演示：

1. **治理护栏拦截**：传入 `Action(command="rm -rf /")` → 断言 `guardrail()` 返回拦截
2. **反馈闭环修正**：构造一个"断言失败"的测试结果 → 通过分类器 + 修正策略引擎 → 断言状态机走向"尝试修正"状态
3. **重点维度演示**：构造多轮修正历史 → 断言状态机在 3 次同策略失败后自动切换策略，6 次总失败后上报人工