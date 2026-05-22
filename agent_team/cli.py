"""CLI for Agent Team - launch, status, stop."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import click

from agent_team.launcher import launch_team, stop_team
from agent_team.tmux import (
    attach_session,
    has_session,
    list_panes,
    session_name,
)


@click.group()
def cli():
    """Agent Team - Multi-model Agent Team orchestration for Claude Code."""
    pass


@cli.command()
@click.option("--leader-provider", default="kimi", help="Leader's model provider")
@click.option("--leader-model", default="kimi-for-coding", help="Leader's model name")
def leader(leader_provider, leader_model):
    """Start a Team Leader for interactive team planning.

    This launches only the Leader Claude Code instance. Use this when you want
    to plan the team configuration through conversation before creating teammates.

    The Leader will have access to:
    - team_list_providers: See available model providers
    - team_list_roles: See available role templates
    - team_create: Dynamically create the team with chosen members

    Example workflow:
        1. agent-team leader
        2. (In Leader) "I need to refactor the auth system"
        3. (Leader plans) "I'll create a team with architect + backend + tester"
        4. (Leader calls team_create)
    """
    team_name = "leader-planning"

    from agent_team.config import build_agent_config, save_team_config
    from agent_team.prompt import build_leader_prompt
    from agent_team.tmux import spawn_member

    config = build_agent_config()
    cwd = os.getcwd()

    # Save minimal team config
    save_team_config(team_name, {
        "name": team_name,
        "leader": {"provider": leader_provider, "model": leader_model},
        "members": [],
        "cwd": cwd,
    })

    # Build leader environment from provider config
    from agent_team.config import generate_env_for_member
    leader_env = generate_env_for_member(leader_provider, leader_model, config.providers)
    leader_env["AGENT_TEAM_AGENT_NAME"] = "leader"
    leader_env["AGENT_TEAM_AGENT_ROLE"] = "leader"

    # Build MCP config
    from agent_team.launcher import _project_mcp_config
    leader_mcp = _project_mcp_config(team_name)
    leader_mcp["mcpServers"]["agent-team"]["env"]["AGENT_TEAM_AGENT_NAME"] = "leader"
    leader_mcp["mcpServers"]["agent-team"]["env"]["AGENT_TEAM_AGENT_ROLE"] = "leader"

    # Leader prompt with planning instructions
    leader_prompt = build_leader_prompt([]) + """

## Team Creation
You have the power to create teams dynamically using your tools:
- team_list_providers: List all available LLM providers and their models
- team_list_roles: List all available role templates
- team_create: Create a team with specific members

## IMPORTANT: Wait for user instructions
Do NOT take any action yet. Do NOT call any tools yet. Do NOT create a team yet.
Simply greet the user, briefly explain your capabilities, and ASK what they want to work on.
Only after the user describes their task should you:
1. Discuss and plan the approach with the user
2. Propose a team composition (roles, providers, models)
3. Wait for user confirmation
4. Then create the team using team_create

You are a collaborative planner, not an autonomous executor. Always confirm with the user before creating teammates.
"""

    click.echo("Starting Team Leader...")
    click.echo("The Leader will launch in a tmux session.")
    click.echo("After planning, use team_create to spawn teammates.")
    click.echo("")

    result = spawn_member(
        team_name=team_name,
        member_name="leader",
        role="leader",
        cwd=cwd,
        env_vars=leader_env,
        mcp_config=leader_mcp,
        prompt_text=leader_prompt,
    )

    click.echo(result)
    click.echo("")
    click.echo("Attach with: agent-team attach -t leader-planning")


@cli.command()
@click.option("--team", "-t", required=True, help="Team name")
@click.option("--leader-provider", default="kimi", help="Leader's model provider")
@click.option("--leader-model", default="kimi-for-coding", help="Leader's model name")
@click.option("--attach", "-a", is_flag=True, help="Attach to tmux session after launch")
@click.argument("members", nargs=-1)
def launch(team, leader_provider, leader_model, attach, members):
    """Launch a complete agent team (Leader + Members) in one command.

    Members can be specified as:
        - Role names from config/roles.yaml: architect backend tester
        - Or explicit provider/model: architect:deepseek:deepseek-v4-pro

    Examples:
        agent-team launch -t myproject architect backend tester
        agent-team launch -t refactor --leader-model claude-sonnet-4-6 architect backend
    """
    parsed_members = []
    for spec in members:
        if ":" in spec:
            parts = spec.split(":")
            if len(parts) == 3:
                parsed_members.append({
                    "name": parts[0],
                    "role": parts[0],
                    "provider": parts[1],
                    "model": parts[2],
                })
            else:
                click.echo(f"Invalid member spec: {spec}. Use name:provider:model")
                sys.exit(1)
        else:
            parsed_members.append({
                "name": spec,
                "role": spec,
            })

    result = launch_team(
        team_name=team,
        leader_provider=leader_provider,
        leader_model=leader_model,
        members=parsed_members,
        attach=attach,
    )
    click.echo(result)


@cli.command()
@click.option("--team", "-t", required=True, help="Team name")
def status(team):
    """Show team status."""
    if not has_session(team):
        click.echo(f"Team '{team}' is not running.")
        return

    panes = list_panes(team)
    click.echo(f"Team: {team}")
    click.echo(f"Session: {session_name(team)}")
    click.echo(f"Panes: {len(panes)}")
    for p in panes:
        click.echo(f"  {p['title']} (pid: {p['pid']})")


@cli.command()
@click.option("--team", "-t", required=True, help="Team name")
@click.option("--cc", is_flag=True, help="Use tmux -CC mode for iTerm2 native rendering")
def attach(team, cc):
    """Attach to a running team session."""
    if not has_session(team):
        click.echo(f"Team '{team}' is not running.")
        return
    import subprocess
    sname = session_name(team)
    if cc or os.environ.get("TERM_PROGRAM") == "iTerm.app":
        env = os.environ.copy()
        env.pop("TMUX", None)
        subprocess.run(["tmux", "-CC", "attach-session", "-t", sname], env=env)
    elif os.environ.get("TMUX"):
        subprocess.run(["tmux", "switch-client", "-t", sname])
    else:
        attach_session(team)


@cli.command()
@click.option("--team", "-t", required=True, help="Team name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def stop(team, yes):
    """Stop a running team and clean up."""
    if not has_session(team):
        click.echo(f"Team '{team}' is not running.")
        return

    if not yes:
        click.confirm(f"Stop team '{team}'?", abort=True)

    result = stop_team(team)
    click.echo(result)


@cli.command()
def list_teams():
    """List all saved team configurations."""
    teams_dir = Path.home() / ".agent-team" / "teams"
    if not teams_dir.exists():
        click.echo("No teams found.")
        return

    for team_dir in sorted(teams_dir.iterdir()):
        if team_dir.is_dir():
            config_path = team_dir / "config.json"
            running = "(running)" if has_session(team_dir.name) else "(stopped)"
            if config_path.exists():
                try:
                    cfg = json.loads(config_path.read_text())
                    members = ", ".join(m["name"] for m in cfg.get("members", []))
                    click.echo(f"  {team_dir.name} {running} - members: {members}")
                except Exception:
                    click.echo(f"  {team_dir.name} {running}")
            else:
                click.echo(f"  {team_dir.name} {running}")


def main():
    cli()


if __name__ == "__main__":
    main()
