# CodingKit

> 一个可观测、可分类、可干预的编码智能体框架（Coding Agent Harness）。

## 核心特性

- **反馈闭环** — 当 agent 生成的代码测试失败时，自动分类失败原因并执行差异化修正策略，而非简单重试
- **可观测状态机** — 修正过程全程可见：当前策略、切换原因、阈值上报，用户可随时干预
- **治理护栏** — 危险操作（删除文件、执行命令等）自动拦截，支持 y/n/m 三种审批决策
- **双界面** — CLI（19 条命令）+ WebUI（实时看板/交互/历史）
- **纯确定性测试** — 所有核心机制使用 MockLLMClient，无需真实 LLM 即可验证

## 快速安装

```bash
pip install codingkit

# 或从源码安装
git clone https://github.com/codingkit/codingkit.git
cd codingkit
pip install -e ".[all,dev]"
```

## 使用

### 快速上手

```bash
codingkit init                              # 初始化当前目录（生成 .codingkit/）
codingkit config key set                    # 录入 API Key（隐藏输入，不落盘明文）
codingkit config model set claude-sonnet-5  # 设默认模型
codingkit run "Write a test for the calculator"
codingkit web                               # 启动 WebUI（http://localhost:8080）
```

### Docker

```bash
docker build -t codingkit .
docker run -it -v ~/.codingkit:/root/.codingkit -v "$PWD:/workspace" codingkit --help
```

### 完整命令参考（19 条）

每条命令都可用 `codingkit <command> --help` 查看详细帮助。

#### 顶层命令（6 条）

| 命令 | 用法 | 说明 |
|------|------|------|
| `init` | `codingkit init` | 在当前目录初始化 CodingKit（生成 `.codingkit/` 配置） |
| `run` | `codingkit run "<task>" [--plan-only]` | 跑一个任务；`--plan-only` 只生成计划不执行 |
| `web` | `codingkit web [-p/--port 8080]` | 启动 WebUI（FastAPI + React），默认绑定 `127.0.0.1:8080` |
| `status` | `codingkit status` | 显示当前配置、工具启用数、最近一次会话 |
| `cancel` | `codingkit cancel` | `run` 在前台运行，无后台任务可取消——命令会诚实说明这一点 |
| `version` | `codingkit version` | 显示版本号 |

#### config 子命令（7 条）

| 命令 | 用法 | 说明 |
|------|------|------|
| `config status` | `codingkit config status` | 显示当前配置（模型、凭据后端、禁用工具等） |
| `config method` | `codingkit config method <keychain\|file>` | 切换凭据存储后端，持久化到 `config.yaml` |
| `config key set` | `codingkit config key set` | 录入/覆盖 API Key（隐藏输入，不落盘明文） |
| `config key show` | `codingkit config key show` | 只显示"已配置/未配置"，**绝不回显明文** |
| `config key delete` | `codingkit config key delete` | 删除已配置的 Key（需确认） |
| `config model list` | `codingkit config model list` | 列出可选 LLM 模型 |
| `config model set` | `codingkit config model set <model_name>` | 设默认模型，持久化到 `config.yaml` |

#### session 子命令（3 条）

| 命令 | 用法 | 说明 |
|------|------|------|
| `session list` | `codingkit session list` | 列出所有会话 |
| `session show` | `codingkit session show <session_id>` | 查看某会话详情（含修正/反馈状态机恢复后的状态） |
| `session delete` | `codingkit session delete <session_id>` | 删除某会话 |

#### tool 子命令（3 条）

| 命令 | 用法 | 说明 |
|------|------|------|
| `tool list` | `codingkit tool list` | 列出全部工具及其启用/禁用状态（✅/❌） |
| `tool enable` | `codingkit tool enable <tool_name>` | 启用某工具，持久化到 `config.yaml` |
| `tool disable` | `codingkit tool disable <tool_name>` | 禁用某工具；禁用后从 LLM 工具定义中剔除、执行时拒绝（优先于护栏审批） |

> SPEC §3.1 要求 18 条命令，本项目额外提供 `config status` 共 19 条。

### 典型工作流

```bash
# 1. 初始化 + 配置凭据与模型
codingkit init
codingkit config method keychain          # 或 file（无桌面环境时）
codingkit config key set
codingkit config model set claude-sonnet-5

# 2. 跑一个任务（前台，多轮自我修正）
codingkit run "Add a multiply function to calc.py with tests"

# 3. 只生成计划，不动文件
codingkit run "Refactor the validator" --plan-only

# 4. 查看历史会话
codingkit session list
codingkit session show <session_id>

# 5. 禁用危险工具后跑任务
codingkit tool disable delete_file
codingkit tool list                         # 确认状态
codingkit run "..."                         # delete_file 不再出现在工具定义里

# 6. 启动 WebUI 看板
codingkit web
```

## 支持的 LLM 提供商

CodingKit 通过模型名**前缀**路由到对应 provider。除 Anthropic（自有 SDK）外，DeepSeek / GLM / Kimi / MiniMax / Qwen 均走 OpenAI 兼容协议，复用同一个 `OpenAIClient`（仅 `base_url` 不同）。

| 前缀 | Provider | base_url | 示例模型 |
|------|----------|----------|---------|
| `claude` | Anthropic | （Anthropic SDK） | `claude-sonnet-5` `claude-opus-5` `claude-haiku-4-5` |
| `gpt` / `o1` / `o3` / `o4` | OpenAI | `api.openai.com` | `gpt-4o` `gpt-4o-mini` `o1` `o3-mini` |
| `deepseek` | DeepSeek | `api.deepseek.com/v1` | `deepseek-chat` `deepseek-reasoner` |
| `glm` | 智谱 GLM | `open.bigmodel.cn/api/paas/v4` | `glm-4.6` `glm-4.5` `glm-4-plus` `glm-4-flash` |
| `kimi` / `moonshot` | Moonshot Kimi | `api.moonshot.cn/v1` | `moonshot-v1-32k` `moonshot-v1-128k` `kimi-k2` |
| `minimax` | MiniMax | `api.minimax.chat/v1` | `MiniMax-M1` `minimax-text-01` `abab6.5s-chat` |
| `qwen` | 通义千问 (DashScope) | `dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-max` `qwen-plus` `qwen-turbo` `qwen3-235b-a22b` |
| `mock` | 测试用 | 无网络 | `mock` |

```bash
codingkit config model list          # 查看全部可选模型
codingkit config model set glm-4.6   # 设默认，按前缀路由
```

> 路由按前缀匹配，所以 provider 新发的模型名（只要保留前缀）无需改代码即可使用。`codingkit config model set` 的大小写不敏感于前缀，但模型名本身会原样传给 provider。

## 凭据安全配置

CodingKit **绝不**把 API Key 写入源码、Git 历史、日志或终端 history。Key 通过独立的凭据子系统管理（详见 `SPEC.md §4.2` 威胁模型）。

### 两种存储后端

| 后端 | 说明 | 适用场景 |
|------|------|---------|
| `keychain`（默认） | 操作系统钥匙串：macOS Keychain / Windows Credential Manager / Linux Secret Service | 桌面环境，推荐 |
| `file` | AES-256-GCM 加密文件 `~/.codingkit/credentials.enc`，主密码由用户输入且**不落盘** | 钥匙串不可用或无桌面环境 |

### 在目标机器上安全配置 Key

```bash
# 首次运行检测到无 Key 时会自动引导录入（隐藏输入）
codingkit config key set

# 查看状态——只显示"已配置/未配置"，绝不回显明文
codingkit config key show

# 更新 / 清除（清除需确认）
codingkit config key set          # 覆盖更新
codingkit config key delete

# 切换存储后端
codingkit config method keychain   # 或 file
```

**Docker 环境下**：容器内无钥匙串，请用 `-v ~/.codingkit:/root/.codingkit` 挂载凭据目录，或首次运行时交互式录入：

```bash
docker run -it -v ~/.codingkit:/root/.codingkit -v "$PWD:/workspace" codingkit \
    config key set
```

> ⚠️ **不要**用 `export API_KEY=...` 的方式：它会进入 shell history，且子进程环境可见明文。始终用上面的 `codingkit config key set`。

## 项目结构

```
src/codingkit/
├── cli/           # CLI 入口（Typer，19 条命令）
├── core/          # 核心：AgentLoop、LLM 抽象、会话管理、上下文构建
├── tools/         # 10 个工具（读/写/编辑/执行/搜索/测试/...）
├── governance/    # 治理护栏 + HITL 审批
├── feedback/      # 反馈闭环：校验器 → 分类器 → 策略引擎 → 回灌器
├── memory/        # 会话记忆（JSON 文件）+ 向量记忆（ChromaDB）
└── web/           # FastAPI 后端 + WebSocket

webui/             # React 前端（Vite + TypeScript）
tests/             # 364 个测试（全部使用 MockLLMClient，不依赖真实 LLM）
demo/              # 3 个确定性演示脚本
```

## 反馈闭环架构

```
测试失败 → 校验器解析 → 分类器分类(8种) → 策略引擎决策
                                            │
                    同一策略失败≥3次 ────────┤→ 自动切换策略
                    总失败≥6次 ──────────────┘→ 上报人工
                                            │
                    回灌器 → 组织修正历史 → 注入 LLM 上下文
```

## 已知限制

- **Python 3.11+**：低于 3.11 不保证可用（使用了 `from __future__ import annotations` 与 `X | Y` 类型语法等特性）。
- **钥匙串后端在 Linux 需 D-Bus / Secret Service**（如 `gnome-keyring`、`kwallet`）。服务器环境通常无 D-Bus，此时会自动降级到 `file`（加密文件）后端；也可直接 `codingkit config method file`。
- **Docker 镜像**需目标机已安装 Docker；容器内对宿主文件系统的读写需通过 `-v` 挂载卷。
- **向量记忆为可选依赖**：`pip install codingkit[memory]` 安装 ChromaDB；缺失时 `MemoryManager` 自动降级到内存存储（跨会话记忆不持久化）。
- **LLM SDK 为可选依赖**：`pip install codingkit[llm]` 安装 `anthropic` / `openai`；只跑 CLI 的 `config`/`session`/`tool` 子命令或跑测试（`MockLLMClient`）无需安装。
- **国产 provider 走 OpenAI 兼容协议**：DeepSeek / GLM / Kimi / MiniMax / Qwen 复用 `OpenAIClient`，仅 `base_url` 不同，无需额外 SDK。但各家对 OpenAI 风格 `tools`（function-calling）的支持程度不一——harness 始终以 OpenAI 格式发送工具定义，不支持 function-calling 的 provider 会在运行时返回 provider 错误（不会静默降级）。
- **WebUI 默认绑定 `127.0.0.1`**，不开放公网；如需远程访问请自行反代并加鉴权。
- **平台**：开发与测试在 Linux / macOS / Windows 上进行；CI 矩阵覆盖 Python 3.11 / 3.12（`ubuntu-latest`）。

## 测试

```bash
pytest tests/ -v        # 364 个测试全部通过
python demo/run_all_demo.sh  # 运行演示脚本
```

## 许可证

MIT