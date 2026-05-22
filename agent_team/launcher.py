"""Core team launch logic - used by CLI and MCP server."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from agent_team.config import build_agent_config, generate_env_for_member, save_team_config
from agent_team.prompt import build_leader_prompt, build_member_prompt
from agent_team.tmux import (
    attach_session,
    has_session,
    kill_session,
    session_name,
    spawn_member,
    tile_panes,
)


def _project_mcp_config(team_name: str) -> dict:
    """Generate MCP server config for a project."""
    project_root = Path(__file__).parent.parent.resolve()
    python_bin = str(project_root / ".venv" / "bin" / "python")
    if not Path(python_bin).exists():
        python_bin = sys.executable
    return {
        "mcpServers": {
            "agent-team": {
                "command": python_bin,
                "args": ["-m", "agent_team.mcp_server"],
                "env": {
                    "AGENT_TEAM_TEAM_NAME": team_name,
                },
            }
        }
    }


def launch_team(
    team_name: str,
    leader_provider: str,
    leader_model: str,
    members: list[dict],
    cwd: str | None = None,
    attach: bool = False,
    skip_leader: bool = False,
) -> str:
    if has_session(team_name) and not skip_leader:
        return f"Team '{team_name}' already exists. Use 'stop' first."

    config = build_agent_config()
    cwd = cwd or os.getcwd()

    resolved_members = []
    for spec in members:
        role_key = spec.get("role", spec["name"])
        role = config.roles.get(role_key)
        if not role:
            return f"Unknown role: {role_key}. Available: {', '.join(config.roles.keys())}"
        provider = spec.get("provider", role.default_provider)
        model = spec.get("model", role.default_model)
        resolved_members.append({
            "name": spec["name"],
            "role": role.name,
            "role_key": role_key,
            "provider": provider,
            "model": model,
        })

    team_config = {
        "name": team_name,
        "leader": {"provider": leader_provider, "model": leader_model},
        "members": resolved_members,
        "cwd": cwd,
    }
    save_team_config(team_name, team_config)

    if not skip_leader:
        leader_env = generate_env_for_member(leader_provider, leader_model, config.providers)
        leader_env["AGENT_TEAM_AGENT_NAME"] = "leader"
        leader_env["AGENT_TEAM_AGENT_ROLE"] = "leader"

        leader_mcp = _project_mcp_config(team_name)
        leader_mcp["mcpServers"]["agent-team"]["env"]["AGENT_TEAM_AGENT_NAME"] = "leader"
        leader_mcp["mcpServers"]["agent-team"]["env"]["AGENT_TEAM_AGENT_ROLE"] = "leader"

        spawn_member(
            team_name=team_name,
            member_name="leader",
            role="leader",
            cwd=cwd,
            env_vars=leader_env,
            mcp_config=leader_mcp,
            prompt_text=build_leader_prompt(resolved_members),
        )

    for spec in resolved_members:
        env = generate_env_for_member(spec["provider"], spec["model"], config.providers)
        env["AGENT_TEAM_AGENT_NAME"] = spec["name"]
        env["AGENT_TEAM_AGENT_ROLE"] = "member"

        mcp_cfg = _project_mcp_config(team_name)
        mcp_cfg["mcpServers"]["agent-team"]["env"]["AGENT_TEAM_AGENT_NAME"] = spec["name"]
        mcp_cfg["mcpServers"]["agent-team"]["env"]["AGENT_TEAM_AGENT_ROLE"] = "member"

        spawn_member(
            team_name=team_name,
            member_name=spec["name"],
            role="member",
            cwd=cwd,
            env_vars=env,
            mcp_config=mcp_cfg,
            prompt_text=build_member_prompt(spec["role"], config.roles[spec["role_key"]].description),
        )
        time.sleep(0.5)

    time.sleep(1)
    tile_panes(team_name)

    if attach:
        attach_session(team_name)

    return f"Team '{team_name}' launched with {len(resolved_members)} members."


def stop_team(team_name: str) -> str:
    if not has_session(team_name):
        return f"Team '{team_name}' is not running."
    kill_session(team_name)
    return f"Team '{team_name}' stopped."
