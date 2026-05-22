# Agent Team 保姆级使用指南

本指南面向第一次使用 Agent Team 的用户，手把手教你从零开始到成功运行一个多 AI 协作团队。

---

## 目录

1. [一句话说明](#一句话说明)
2. [环境准备](#环境准备)
3. [安装项目](#安装项目)
4. [配置 API Key](#配置-api-key)
5. [案例一：Leader 模式 — 对话规划团队](#案例一leader-模式--对话规划团队)
6. [案例二：一键启动 — 直接指定团队](#案例二一键启动--直接指定团队)
7. [案例三：iTerm2 最佳体验](#案例三iterm2-最佳体验)
8. [Agent 之间怎么通信](#agent-之间怎么通信)
9. [文件锁怎么用](#文件锁怎么用)
10. [常见问题排查](#常见问题排查)
11. [命令大全](#命令大全)

---

## 一句话说明

Agent Team 让你在一个 tmux session 里同时运行多个 Claude Code 实例，每个用不同的 LLM（Kimi、DeepSeek、MiniMax 等），它们之间可以互相发消息、分配任务、避免文件冲突。

---

## 环境准备

> 以下所有命令都在 **macOS 终端** 中执行（Terminal.app 或 iTerm2 都行）

### 第 1 步：安装 Homebrew

如果你还没有 Homebrew：

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

安装完后根据提示添加环境变量：

```bash
# Apple Silicon Mac (M1/M2/M3/M4)
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

验证：`brew --version` 看到版本号即可。

### 第 2 步：安装 tmux

```bash
brew install tmux
```

验证：`tmux -V` 应输出类似 `tmux 3.5`。

### 第 3 步：安装 iTerm2（推荐）

```bash
brew install --cask iterm2
```

安装后在 Launchpad 中打开 iTerm2。

---

## 安装项目

```bash
# 进入项目目录
cd /path/to/teammate_capacatity_builder

# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境（每次新开终端都需要）
source .venv/bin/activate

# 安装
pip install -e .
```

验证：`agent-team --help` 看到帮助信息即可。

---

## 配置 API Key

编辑 `~/.zshrc`（或 `~/.bashrc`），添加你的 API Key：

```bash
export KIMI_API_KEY="sk-..."
export DEEPSEEK_API_KEY="sk-..."
export MINIMAX_API_KEY="sk-..."
```

保存后执行 `source ~/.zshrc` 使其生效。

然后编辑项目中的 `config/providers.yaml`，确认 provider 配置正确：

```yaml
providers:
  kimi:
    name: Kimi
    base_url: https://api.moonshot.cn/v1
    auth_token: ${KIMI_API_KEY}
    models:
      kimi-for-coding:
        name: kimi-for-coding

  deepseek:
    name: DeepSeek
    base_url: https://api.deepseek.com/v1
    auth_token: ${DEEPSEEK_API_KEY}
    models:
      deepseek-v4-pro:
        name: deepseek-chat
```

角色模板在 `config/roles.yaml` 中配置，定义每个角色的默认 provider 和 model。

---

## 案例一：Leader 模式 — 对话规划团队

这是最推荐的使用方式。你先启动一个 Leader，和它对话讨论需求，然后由它来创建合适的团队。

### 操作步骤

**在你的终端中执行：**

```bash
# 确保已激活虚拟环境
source .venv/bin/activate

# 启动 Leader
agent-team leader
```

输出类似：
```
Starting Team Leader...
Member 'leader' spawned in agent-team-leader-planning:leader
Attach with: agent-team attach -t leader-planning
```

**然后 attach 到 session 和 Leader 对话：**

```bash
agent-team attach -t leader-planning
```

> 如果你用 iTerm2，会自动用 `-CC` 模式打开原生窗口。

### 对话示例

你进入 Leader 的 Claude Code 界面后，像正常聊天一样：

```
你：我有一个 Python 项目需要重构支付模块，帮我组建团队

Leader：好的，让我看看有哪些可用的 provider 和角色...
       (调用 team_list_providers)
       (调用 team_list_roles)
       
       根据你的需求，我建议这样的团队配置：
       - architect (DeepSeek): 负责设计新的支付架构
       - backend (Kimi): 负责代码实现
       - tester (MiniMax): 负责编写测试和验证
       
       你觉得这个配置可以吗？

你：可以，创建吧

Leader：(调用 team_create)
       团队已创建！3 个 teammate 已经在各自的 tmux pane 中启动。
       我现在开始分配任务...
```

### 团队创建后

Leader 会自动：
1. 创建任务（`team_create_task`）
2. 给 teammate 发消息分配工作（`team_send_message`）
3. Teammate 收到消息后自动被唤醒（auto-wake）
4. Teammate 认领任务、执行、报告完成
5. Leader 收到报告后决定下一步

你可以随时在 Leader 的对话框中输入新指令，比如：
```
你：让 tester 重点测试边界情况
你：停下来，我要改一下需求
你：当前进度怎么样？
```

---

## 案例二：一键启动 — 直接指定团队

如果你已经知道需要什么团队配置，可以跳过规划直接启动：

**在你的终端中执行：**

```bash
# 启动一个包含 architect + backend + tester 的团队
agent-team launch -t myproject architect backend tester
```

也可以指定具体的 provider 和 model：

```bash
agent-team launch -t myproject \
  architect:deepseek:deepseek-v4-pro \
  backend:kimi:kimi-for-coding \
  tester:minimax:MiniMax-M2.5
```

启动后 attach：

```bash
agent-team attach -t myproject
```

---

## 案例三：iTerm2 最佳体验

iTerm2 的 `tmux -CC` 控制模式可以把 tmux pane 渲染为原生 iTerm2 标签页，体验最好。

### 方法 A：先启动再 attach（推荐）

```bash
# 第 1 步：正常启动（在普通终端中）
agent-team leader

# 第 2 步：用 tmux -CC 模式 attach（iTerm2 会弹出原生窗口）
tmux -CC attach -t agent-team-leader-planning
```

### 方法 B：用 agent-team attach（自动检测 iTerm2）

```bash
agent-team leader
agent-team attach -t leader-planning    # 在 iTerm2 中自动用 -CC 模式
```

### 方法 C：强制 -CC 模式

```bash
agent-team attach -t leader-planning --cc
```

---

## Agent 之间怎么通信

所有通信通过 MCP 工具完成。Agent 不需要知道底层实现，只需要调用工具。

### 发消息

```
# 给特定 agent 发消息
team_send_message(to="backend", content="请实现用户注册 API")

# 广播给所有人
team_send_message(to="all", content="代码冻结，准备发布")
```

### 读消息

```
# 只看未读消息
team_get_messages(unread_only=true)

# 看所有消息
team_get_messages(limit=50)
```

### Auto-wake 机制

当 Agent A 给 Agent B 发消息时：
1. 消息写入 SQLite 数据库
2. 系统检测 Agent B 是否空闲（在等待用户输入）
3. 如果空闲，通过 tmux 自动发送提示唤醒 Agent B
4. Agent B 被唤醒后调用 `team_get_messages()` 读取消息

**你不需要手动做任何事情**，消息会自动送达。

---

## 文件锁怎么用

当多个 agent 可能同时编辑同一个文件时，必须用锁：

```
# 编辑前：获取锁
team_acquire_lock(file_path="src/payment.py")
→ 成功：可以编辑
→ 失败：文件被 xxx 锁定，等待或换一个文件

# 编辑完成后：释放锁
team_release_lock(file_path="src/payment.py")

# 不确定时：检查锁状态
team_check_lock(file_path="src/payment.py")
```

**规则**（写在每个 agent 的 system prompt 里，它们会自动遵守）：
- 编辑前必须 acquire_lock
- 如果被锁，不能编辑，等待或换文件
- 编辑完必须立即 release_lock
- 读文件不需要锁

---

## 常见问题排查

### Q: Agent 收不到消息？

**原因 1**：Agent 正在执行任务（不是空闲状态），auto-wake 不会触发。
**解决**：消息已存在数据库中，等 agent 完成当前任务后调用 `team_get_messages()` 就能看到。

**原因 2**：tmux pane 名称不匹配。
**解决**：检查 `tmux list-windows -t agent-team-leader-planning`。

### Q: Leader 自己就开始建团队了？

旧版本的 bug，已修复。如果还出现，确认你用的是最新代码：
```bash
pip install -e .
```

### Q: tmux 嵌套报错 "sessions should be nested with care"？

你已经在一个 tmux session 里了。解决方法：
```bash
# 方法 1：用 switch-client
tmux switch-client -t agent-team-leader-planning

# 方法 2：退出当前 tmux 再 attach
tmux detach
tmux -CC attach -t agent-team-leader-planning
```

### Q: 怎么清理所有进程重来？

```bash
# 停止团队
agent-team stop -t leader-planning -y

# 如果上面不管用，手动清理
tmux kill-session -t agent-team-leader-planning
pkill -f "agent_team.mcp_server"
```

### Q: 锁没释放怎么办？

Agent 崩溃可能导致锁未释放：
```python
from agent_team.db import TeamDB
db = TeamDB("leader-planning")
db.release_all_locks("crashed-agent-name")
db.close()
```

---

## 命令大全

所有命令在**你的普通终端**中执行：

| 命令 | 说明 | 在哪里执行 |
|------|------|-----------|
| `agent-team leader` | 启动 Leader（交互规划模式） | 终端 |
| `agent-team attach -t NAME` | 附加到团队 session | 终端 |
| `agent-team attach -t NAME --cc` | 强制 iTerm2 控制模式 | 终端 |
| `agent-team launch -t NAME roles...` | 一键启动完整团队 | 终端 |
| `agent-team status -t NAME` | 查看团队状态 | 终端 |
| `agent-team stop -t NAME -y` | 停止团队 | 终端 |
| `agent-team list-teams` | 列出所有团队 | 终端 |

以下是 **Agent 内部使用的 MCP 工具**（你不需要手动调用，Agent 会自动使用）：

| 工具 | 谁用 | 说明 |
|------|------|------|
| `team_send_message(to, content)` | 所有人 | 发消息 |
| `team_get_messages(limit, unread_only)` | 所有人 | 读消息 |
| `team_create_task(subject, description)` | Leader | 创建任务 |
| `team_get_tasks(pending_only)` | Member | 查看任务 |
| `team_claim_task(task_id)` | Member | 认领任务 |
| `team_report(task_id, summary)` | Member | 报告完成 |
| `team_acquire_lock(file_path)` | Member | 获取文件锁 |
| `team_release_lock(file_path)` | Member | 释放文件锁 |
| `team_status()` | Leader | 查看全局状态 |
| `team_create(members)` | Leader | 动态创建团队 |
