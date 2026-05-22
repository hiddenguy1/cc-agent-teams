# Agent Team — 多模型 AI Agent 协作框架

## 要解决什么问题

Claude Code 的原生 Agent 模式有三个限制：

1. **Agent 之间不能直接通信** — 只有 parent 能和 child 通信，sibling 之间互相看不到
2. **只能用单一 LLM Provider** — 所有 agent 必须用同一个 API
3. **多 Agent 并行编辑会冲突** — 没有文件锁机制，两个 agent 同时改一个文件就出问题

Agent Team 解决这三个问题，让你可以组建一个**多模型、可互相通信、有冲突保护**的 AI 团队。

## 做了哪些改进

### v2 架构（当前版本）

| 改进点 | 旧方案 | 新方案 |
|--------|--------|--------|
| 存储 | FastAPI Hub + JSONL 文件 | SQLite（WAL 模式，多进程安全） |
| 消息通知 | 轮询（agent 可能永远收不到） | Auto-wake（tmux send-keys 主动唤醒） |
| 广播消息 | 写入 all.jsonl 但没人读 | SQL 查询 `WHERE to=? OR to='all'` |
| 已读/未读 | 无 | read_by 字段追踪 |
| 进程管理 | 需要单独启动 Hub 进程 | 无需额外进程 |
| 端口冲突 | Hub 占用 8765 端口 | 不使用网络端口 |
| Leader 行为 | 启动后立即自主行动 | 等待用户指示再规划 |

### 架构图

```
┌─────────────────────────────────────────────────┐
│              tmux session                        │
│  ┌────────┐  ┌────────┐  ┌────────┐            │
│  │ Leader │  │Worker-1│  │Worker-2│  ...       │
│  │ (Kimi) │  │(Deep   │  │(Mini   │            │
│  │        │  │ Seek)  │  │ Max)   │            │
│  └───┬────┘  └───┬────┘  └───┬────┘            │
│      │           │           │                  │
│      └───────────┼───────────┘                  │
│                  ▼                               │
│        ┌──────────────────┐                     │
│        │  SQLite (WAL)    │                     │
│        │  + Auto-wake     │                     │
│        └──────────────────┘                     │
└─────────────────────────────────────────────────┘
```

## 安装

```bash
cd teammate_capacatity_builder
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

前置依赖：
- Python 3.12+
- tmux（`brew install tmux`）
- iTerm2 推荐（`brew install --cask iterm2`）

## 配置 API Key

```bash
# 在 ~/.zshrc 或 ~/.bashrc 中添加
export KIMI_API_KEY="sk-..."
export DEEPSEEK_API_KEY="sk-..."
export MINIMAX_API_KEY="sk-..."
```

Provider 和 Role 的详细配置见 `config/providers.yaml` 和 `config/roles.yaml`。

## 命令速查

所有命令在**你的普通终端**中执行（不是在 tmux 或 Claude Code 里面）：

```bash
# 启动 Leader（交互式规划模式）
agent-team leader

# 附加到团队 session（在 iTerm2 中自动用 -CC 模式）
agent-team attach -t leader-planning

# 一键启动完整团队（跳过规划，直接指定成员）
agent-team launch -t myproject architect backend tester

# 查看团队状态
agent-team status -t myproject

# 停止团队（杀掉所有 agent 进程）
agent-team stop -t myproject -y

# 列出所有团队
agent-team list-teams
```

## 项目结构

```
agent_team/
├── db.py           # SQLite 存储层（消息、锁、任务）
├── wake.py         # Auto-wake 机制（tmux send-keys 唤醒）
├── mcp_server.py   # MCP Server（Claude Code 的工具接口）
├── launcher.py     # 团队启动逻辑
├── tmux.py         # tmux 控制
├── prompt.py       # Agent system prompt 生成
├── config.py       # 配置加载
├── models.py       # 数据模型
└── cli.py          # CLI 入口

config/
├── providers.yaml  # LLM Provider 配置
└── roles.yaml      # 角色模板
```

## 详细使用指南

见 [docs/USER_GUIDE.md](docs/USER_GUIDE.md)。
