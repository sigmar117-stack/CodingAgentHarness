# CodingKit

> 一个可观测、可分类、可干预的编码智能体框架（Coding Agent Harness）。

## 核心特性

- **反馈闭环** — 当 agent 生成的代码测试失败时，自动分类失败原因并执行差异化修正策略，而非简单重试
- **可观测状态机** — 修正过程全程可见：当前策略、切换原因、阈值上报，用户可随时干预
- **治理护栏** — 危险操作（删除文件、执行命令等）自动拦截，支持 y/n/m 三种审批决策
- **双界面** — CLI（18 条命令）+ WebUI（实时看板/交互/历史）
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

```bash
# CLI
codingkit run "Write a test for the calculator"
codingkit web          # 启动 WebUI（http://localhost:8080）
codingkit --help       # 查看全部 18 条命令

# Docker
docker build -t codingkit .
docker run -it codingkit --help
```

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
├── cli/           # CLI 入口（Typer，18 条命令）
├── core/          # 核心：AgentLoop、LLM 抽象、会话管理、上下文构建
├── tools/         # 10 个工具（读/写/编辑/执行/搜索/测试/...）
├── governance/    # 治理护栏 + HITL 审批
├── feedback/      # 反馈闭环：校验器 → 分类器 → 策略引擎 → 回灌器
├── memory/        # 会话记忆（JSON 文件）+ 向量记忆（ChromaDB）
└── web/           # FastAPI 后端 + WebSocket

webui/             # React 前端（Vite + TypeScript）
tests/             # 326 个测试（全部使用 MockLLMClient）
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
- **WebUI 默认绑定 `127.0.0.1`**，不开放公网；如需远程访问请自行反代并加鉴权。
- **平台**：开发与测试在 Linux / macOS / Windows 上进行；CI 矩阵覆盖 Python 3.11 / 3.12（`ubuntu-latest`）。

## 测试

```bash
pytest tests/ -v        # 326 个测试全部通过
python demo/run_all_demo.sh  # 运行演示脚本
```

## 许可证

MIT