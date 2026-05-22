"""Auto-wake mechanism: notify idle agents of new messages via tmux."""

from __future__ import annotations

import os
import subprocess
import tempfile
import time


def _is_agent_idle(target: str) -> bool:
    """Check if a Claude Code agent is idle (waiting for user input)."""
    result = subprocess.run(
        ["tmux", "capture-pane", "-p", "-t", target],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return False
    lines = [ln.strip() for ln in result.stdout.splitlines() if ln.strip()]
    tail = lines[-5:] if len(lines) >= 5 else lines
    for line in tail:
        if line.startswith(("❯", ">", "›")):
            return True
    return False


def wake_agent(team_name: str, agent_name: str) -> bool:
    """Send a wake prompt to an idle agent via tmux paste-buffer + Enter."""
    target = f"agent-team-{team_name}:{agent_name}"
    if not _is_agent_idle(target):
        return False

    prompt = "[System] You have new messages. Call team_get_messages() now to read them."
    buf_name = f"wake-{team_name}-{agent_name}"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, prefix="agent-team-wake-") as f:
        f.write(prompt)
        tmp_path = f.name

    try:
        subprocess.run(["tmux", "load-buffer", "-b", buf_name, tmp_path], capture_output=True)
        subprocess.run(["tmux", "paste-buffer", "-b", buf_name, "-t", target], capture_output=True)
        time.sleep(0.3)
        subprocess.run(["tmux", "send-keys", "-t", target, "Enter"], capture_output=True)
        time.sleep(0.2)
        subprocess.run(["tmux", "send-keys", "-t", target, "Enter"], capture_output=True)
        subprocess.run(["tmux", "delete-buffer", "-b", buf_name], capture_output=True)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    return True
