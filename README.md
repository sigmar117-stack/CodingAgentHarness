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

## 测试

```bash
pytest tests/ -v        # 326 个测试全部通过
python demo/run_all_demo.sh  # 运行演示脚本
```

## 许可证

MIT