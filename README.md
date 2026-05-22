# Agent Team — 多模型 AI Agent 协作框架

## 这是什么

Agent Team 让你在本地同时运行多个 Claude Code 实例，每个连接不同的 LLM（Kimi、DeepSeek、MiniMax 等），组成一个可以互相通信、协同工作的 AI 团队。

**核心能力：**

- **多模型混用** — 不同角色用不同模型（贵的做决策，便宜的做执行）
- **Agent 间直接通信** — 任意 agent 可以给任意 agent 发消息，不限于 leader-worker 单向
- **文件冲突保护** — 原子级文件锁，防止多 agent 同时编辑同一文件
- **自动唤醒** — 消息发出后自动通知接收者，无需轮询
- **已读追踪** — 每条消息有已读/未读状态

### 架构

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

- 无需额外服务进程，所有 Agent 通过 SQLite 直接读写共享状态
- 消息发送后通过 tmux 自动唤醒空闲的接收者
- SQLite WAL 模式支持多进程并发安全读写

## 安装

```bash
cd teammate_capacatity_builder
## python venv 
python3 -m venv .venv
## or uv (recommand)
uv venv .venv
source .venv/bin/activate
pip install -e .
```

```bash
## or anaconda
conda create -n teammate_builder python==3.12
conda activate teammate_builder
pip install -e . 
```

前置依赖：
- Python 3.12+
- tmux（`brew install tmux`）
- iTerm2 推荐（`brew install --cask iterm2`）

## 配置 API Key

```bash
# 在 ~/.zshrc 或 ~/.bashrc 中添加(不建议)
export KIMI_API_KEY="sk-..."
export DEEPSEEK_API_KEY="sk-..."
export MINIMAX_API_KEY="sk-..."
```


**建议直接在.yaml文件中修改.** Provider 和 Role 的详细配置见 `config/providers_example.yaml` 和 `config/roles.yaml`。


## 命令速查

所有命令在**你的普通终端**中执行（不是在 tmux 或 Claude Code 里面）：

```bash
# 启动 Leader（交互式规划模式，先和你对话再建团队）
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
