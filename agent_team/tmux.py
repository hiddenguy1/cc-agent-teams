"""Tmux control utilities for spawning agent team members."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile
import time
from pathlib import Path


def _has_tmux() -> bool:
    return shutil.which("tmux") is not None


def session_name(team_name: str) -> str:
    return f"agent-team-{team_name}"


def has_session(team_name: str) -> bool:
    return subprocess.run(
        ["tmux", "has-session", "-t", session_name(team_name)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0


def create_session(team_name: str, window_name: str, command: str) -> bool:
    sname = session_name(team_name)
    result = subprocess.run(
        ["tmux", "new-session", "-d", "-s", sname, "-n", window_name, command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0


def create_window(team_name: str, window_name: str, command: str) -> bool:
    sname = session_name(team_name)
    result = subprocess.run(
        ["tmux", "new-window", "-t", sname, "-n", window_name, command],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0


def send_keys(target: str, keys: str) -> bool:
    result = subprocess.run(
        ["tmux", "send-keys", "-t", target, keys, "Enter"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0


def capture_pane(target: str, lines: int = 50) -> str:
    result = subprocess.run(
        ["tmux", "capture-pane", "-p", "-t", target, "-S", f"-{lines}"],
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else ""


def tile_panes(team_name: str) -> str:
    """Merge all windows into one tiled view."""
    sname = session_name(team_name)

    if not has_session(team_name):
        return f"Session {sname} not found"

    # Count panes in window 0
    pane_result = subprocess.run(
        ["tmux", "list-panes", "-t", f"{sname}:0"],
        capture_output=True,
        text=True,
    )
    num_panes = len(pane_result.stdout.strip().splitlines()) if pane_result.returncode == 0 else 0

    # List windows
    win_result = subprocess.run(
        ["tmux", "list-windows", "-t", sname, "-F", "#{window_index}"],
        capture_output=True,
        text=True,
    )
    if win_result.returncode != 0:
        return f"Error listing windows: {win_result.stderr}"

    windows = win_result.stdout.strip().splitlines()

    if len(windows) <= 1 and num_panes > 1:
        return f"Already tiled ({num_panes} panes)"

    # Join all windows into window 0
    if len(windows) > 1:
        first = windows[0]
        for w in windows[1:]:
            subprocess.run(
                ["tmux", "join-pane", "-s", f"{sname}:{w}", "-t", f"{sname}:{first}", "-h"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        subprocess.run(
            ["tmux", "select-layout", "-t", f"{sname}:{first}", "tiled"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    return "Tiled successfully"


def attach_session(team_name: str) -> None:
    sname = session_name(team_name)
    subprocess.run(["tmux", "attach-session", "-t", sname])


def kill_session(team_name: str) -> bool:
    sname = session_name(team_name)
    result = subprocess.run(
        ["tmux", "kill-session", "-t", sname],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0


def spawn_member(
    team_name: str,
    member_name: str,
    role: str,
    cwd: str,
    env_vars: dict[str, str],
    mcp_config: dict,
    prompt_text: str | None = None,
) -> str:
    """Spawn a team member in a tmux window."""
    if not _has_tmux():
        return "Error: tmux not installed"

    sname = session_name(team_name)
    target = f"{sname}:{member_name}"

    # Build environment exports
    all_env = dict(os.environ)
    all_env.update(env_vars)
    all_env.update({
        "AGENT_TEAM_AGENT_NAME": member_name,
        "AGENT_TEAM_AGENT_ROLE": role,
        "AGENT_TEAM_TEAM_NAME": team_name,
        "AGENT_TEAM_HUB_URL": f"http://127.0.0.1:8765",
    })
    # Unset Claude nesting detection so spawned claude doesn't refuse
    for key in ["CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SESSION"]:
        all_env.pop(key, None)

    export_str = "; ".join(f"export {k}={shlex.quote(v)}" for k, v in all_env.items())

    # Write MCP config to per-member file so they don't overwrite each other
    team_mcp_dir = Path.home() / ".agent-team" / "teams" / team_name / "mcp-configs"
    team_mcp_dir.mkdir(parents=True, exist_ok=True)
    mcp_path = team_mcp_dir / f"{member_name}.json"
    with mcp_path.open("w", encoding="utf-8") as f:
        import json
        json.dump(mcp_config, f, indent=2)

    # Build command: cd to worktree, launch claude with per-member MCP config
    cmd = f"cd {shlex.quote(cwd)} && claude --dangerously-skip-permissions --mcp-config {shlex.quote(str(mcp_path))}"

    full_cmd = f"{export_str}; {cmd}"

    # Create session or window
    if not has_session(team_name):
        ok = create_session(team_name, member_name, full_cmd)
    else:
        ok = create_window(team_name, member_name, full_cmd)

    if not ok:
        return f"Error: failed to spawn {member_name}"

    # Wait for startup
    time.sleep(1)

    # Send prompt if provided (for interactive claude)
    if prompt_text:
        _send_prompt_to_claude(target, prompt_text)

    return f"Member '{member_name}' spawned in {target}"


def _send_prompt_to_claude(target: str, prompt: str) -> None:
    """Send initial prompt to a Claude Code tmux pane."""
    # Wait for claude to be ready
    _wait_for_claude_ready(target, timeout_seconds=15)

    # Write to temp file and paste
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, prefix="agent-team-prompt-") as f:
        f.write(prompt)
        tmp_path = f.name

    subprocess.run(["tmux", "load-buffer", "-b", f"prompt-{target}", tmp_path], capture_output=True)
    subprocess.run(["tmux", "paste-buffer", "-b", f"prompt-{target}", "-t", target], capture_output=True)
    time.sleep(0.5)
    subprocess.run(["tmux", "send-keys", "-t", target, "Enter"], capture_output=True)
    time.sleep(0.3)
    subprocess.run(["tmux", "send-keys", "-t", target, "Enter"], capture_output=True)
    subprocess.run(["tmux", "delete-buffer", "-b", f"prompt-{target}"], capture_output=True)
    os.unlink(tmp_path)


def _wait_for_claude_ready(target: str, timeout_seconds: float = 15.0, poll_interval: float = 0.5) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        pane = subprocess.run(
            ["tmux", "capture-pane", "-p", "-t", target],
            capture_output=True,
            text=True,
        )
        if pane.returncode == 0:
            lines = [ln.strip() for ln in pane.stdout.splitlines() if ln.strip()]
            tail = lines[-5:] if len(lines) >= 5 else lines
            for line in tail:
                if line.startswith(("❯", ">", "›")):
                    return True
        time.sleep(poll_interval)
    return False


def list_panes(team_name: str) -> list[dict]:
    """List all panes in the team session."""
    sname = session_name(team_name)
    result = subprocess.run(
        ["tmux", "list-panes", "-t", f"{sname}:0", "-F", "#{pane_id}|#{pane_title}|#{pane_pid}"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    panes = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("|")
        if len(parts) >= 3:
            panes.append({"id": parts[0], "title": parts[1], "pid": parts[2]})
    return panes
