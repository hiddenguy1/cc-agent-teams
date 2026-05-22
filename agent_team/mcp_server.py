"""MCP Server for Agent Team - stdio transport, direct SQLite access."""

from __future__ import annotations

import os
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from agent_team.db import TeamDB
from agent_team.wake import wake_agent

AGENT_NAME = os.environ.get("AGENT_TEAM_AGENT_NAME", "unknown")
AGENT_ROLE = os.environ.get("AGENT_TEAM_AGENT_ROLE", "member")
TEAM_NAME = os.environ.get("AGENT_TEAM_TEAM_NAME", "default")

_db: TeamDB | None = None


def _get_db() -> TeamDB:
    global _db
    if _db is None:
        _db = TeamDB(TEAM_NAME)
    return _db


# ── Leader tools ───────────────────────────────────────────────────

LEADER_TOOLS: list[Tool] = [
    Tool(
        name="team_list_providers",
        description="List all available LLM providers and their models.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="team_list_roles",
        description="List all available role templates.",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="team_create",
        description="Create a team with specified members.",
        inputSchema={
            "type": "object",
            "properties": {
                "members": {
                    "type": "array",
                    "description": "List of team members",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "role": {"type": "string"},
                            "provider": {"type": "string"},
                            "model": {"type": "string"},
                        },
                        "required": ["name"],
                    },
                },
            },
            "required": ["members"],
        },
    ),
    Tool(
        name="team_create_task",
        description="Create a new task for a teammate.",
        inputSchema={
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "description": {"type": "string"},
                "blocked_by": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["subject"],
        },
    ),
    Tool(
        name="team_status",
        description="Get full team status: members, locks, tasks.",
        inputSchema={"type": "object", "properties": {}},
    ),
]

# ── Member tools ───────────────────────────────────────────────────

MEMBER_TOOLS: list[Tool] = [
    Tool(
        name="team_get_tasks",
        description="List tasks. Check for new tasks to claim.",
        inputSchema={
            "type": "object",
            "properties": {"pending_only": {"type": "boolean"}},
        },
    ),
    Tool(
        name="team_claim_task",
        description="Claim a pending task.",
        inputSchema={
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    ),
    Tool(
        name="team_report",
        description="Report task completion to the leader.",
        inputSchema={
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "summary": {"type": "string"},
                "files_changed": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["task_id", "summary"],
        },
    ),
    Tool(
        name="team_acquire_lock",
        description="Lock a file before editing. MUST call before Edit/Write.",
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "task_id": {"type": "string"},
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="team_release_lock",
        description="Release a file lock after editing.",
        inputSchema={
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"],
        },
    ),
    Tool(
        name="team_check_lock",
        description="Check if a file is locked and by whom.",
        inputSchema={
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
            "required": ["file_path"],
        },
    ),
]

# ── Shared tools ───────────────────────────────────────────────────

SHARED_TOOLS: list[Tool] = [
    Tool(
        name="team_send_message",
        description="Send a message to a teammate or broadcast to all.",
        inputSchema={
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient name or 'all'"},
                "content": {"type": "string"},
            },
            "required": ["to", "content"],
        },
    ),
    Tool(
        name="team_get_messages",
        description="Check inbox for new messages. Called automatically via auto-wake when messages arrive.",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
                "unread_only": {"type": "boolean", "default": True},
            },
        },
    ),
]

# ── Tool handler ──────────────────────────────────────────────────

async def handle_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    try:
        db = _get_db()

        if name == "team_send_message":
            to = arguments["to"]
            msg_id = db.send_message(AGENT_NAME, to, arguments["content"])
            try:
                if to == "all":
                    from agent_team.config import load_team_config
                    cfg = load_team_config(TEAM_NAME)
                    for m in cfg.get("members", []):
                        if m["name"] != AGENT_NAME:
                            wake_agent(TEAM_NAME, m["name"])
                    if AGENT_NAME != "leader":
                        wake_agent(TEAM_NAME, "leader")
                else:
                    wake_agent(TEAM_NAME, to)
            except Exception:
                pass
            return [TextContent(type="text", text=f"Message sent: {msg_id}")]

        elif name == "team_get_messages":
            limit = arguments.get("limit", 20)
            unread_only = arguments.get("unread_only", True)
            messages = db.get_messages(AGENT_NAME, limit, unread_only)
            if not messages:
                return [TextContent(type="text", text="No new messages.")]
            db.mark_read(AGENT_NAME, [m["id"] for m in messages])
            lines = [f"--- Messages ({len(messages)}) ---"]
            for m in messages:
                lines.append(f"[{m['from_agent']}] {m['content']}")
            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "team_list_providers":
            from agent_team.config import build_agent_config
            config = build_agent_config()
            lines = ["=== Available Providers ==="]
            for key, provider in config.providers.items():
                lines.append(f"\n{key}: {provider.name}")
                for mk, mv in provider.models.items():
                    lines.append(f"  - {mk}")
            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "team_list_roles":
            from agent_team.config import build_agent_config
            config = build_agent_config()
            lines = ["=== Available Roles ==="]
            for key, role in config.roles.items():
                lines.append(f"\n{key}: {role.name} - {role.description}")
            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "team_create":
            from agent_team.config import load_team_config
            from agent_team.launcher import launch_team
            members = arguments.get("members", [])
            team_cfg = load_team_config(TEAM_NAME)
            leader = team_cfg.get("leader", {})
            result = launch_team(
                team_name=TEAM_NAME,
                leader_provider=leader.get("provider", "kimi"),
                leader_model=leader.get("model", "kimi-for-coding"),
                members=members,
                skip_leader=True,
            )
            return [TextContent(type="text", text=result)]

        elif name == "team_create_task":
            task = db.create_task(
                arguments["subject"],
                arguments.get("description", ""),
                arguments.get("blocked_by"),
            )
            return [TextContent(type="text", text=f"Task created: {task['id']}")]

        elif name == "team_status":
            from agent_team.config import load_team_config
            cfg = load_team_config(TEAM_NAME)
            lines = [f"=== Team: {TEAM_NAME} ==="]
            lines.append("\nMembers:")
            for m in cfg.get("members", []):
                lines.append(f"  {m['name']} ({m.get('provider', '')}/{m.get('model', '')})")
            locks = db.list_locks()
            lines.append(f"\nLocks: {len(locks)}")
            for f, lock in locks.items():
                lines.append(f"  {f} -> {lock['agent']}")
            tasks = db.get_tasks()
            lines.append(f"\nTasks: {len(tasks)}")
            for t in tasks:
                lines.append(f"  [{t['status']}] {t['id']}: {t['subject']} (owner: {t.get('owner') or 'unassigned'})")
            unread = db.get_unread_count("leader")
            lines.append(f"\nUnread reports for leader: {unread}")
            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "team_get_tasks":
            tasks = db.get_tasks(pending_only=arguments.get("pending_only", False))
            if not tasks:
                return [TextContent(type="text", text="No tasks.")]
            lines = ["--- Tasks ---"]
            for t in tasks:
                lines.append(f"[{t['status']}] {t['id']}: {t['subject']} (owner: {t.get('owner') or 'unassigned'})")
            return [TextContent(type="text", text="\n".join(lines))]

        elif name == "team_claim_task":
            ok = db.claim_task(arguments["task_id"], AGENT_NAME)
            if ok:
                return [TextContent(type="text", text=f"Task {arguments['task_id']} claimed.")]
            return [TextContent(type="text", text=f"Failed to claim task. It may already be assigned.")]

        elif name == "team_report":
            task_id = arguments["task_id"]
            db.complete_task(task_id, AGENT_NAME)
            db.send_message(
                AGENT_NAME, "leader", arguments["summary"],
                msg_type="report",
                metadata={"task_id": task_id, "files_changed": arguments.get("files_changed", [])},
            )
            try:
                wake_agent(TEAM_NAME, "leader")
            except Exception:
                pass
            return [TextContent(type="text", text=f"Report sent for task {task_id}.")]

        elif name == "team_acquire_lock":
            ok = db.acquire_lock(AGENT_NAME, arguments["file_path"], arguments.get("task_id", ""))
            if ok:
                return [TextContent(type="text", text=f"Lock acquired for {arguments['file_path']}")]
            lock = db.check_lock(arguments["file_path"])
            return [TextContent(type="text", text=f"File is locked by {lock['agent'] if lock else 'unknown'}. Wait or choose another file.")]

        elif name == "team_release_lock":
            ok = db.release_lock(AGENT_NAME, arguments["file_path"])
            if ok:
                return [TextContent(type="text", text=f"Lock released for {arguments['file_path']}")]
            return [TextContent(type="text", text=f"Failed to release lock. You may not own it.")]

        elif name == "team_check_lock":
            lock = db.check_lock(arguments["file_path"])
            if lock:
                return [TextContent(type="text", text=f"Locked by {lock['agent']} since {lock['acquired_at']}")]
            return [TextContent(type="text", text=f"{arguments['file_path']} is not locked.")]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        return [TextContent(type="text", text=f"Error: {type(e).__name__}: {e}")]


async def main():
    is_leader = AGENT_ROLE == "leader"
    tools = SHARED_TOOLS + (LEADER_TOOLS if is_leader else MEMBER_TOOLS)

    server = Server("agent-team")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None = None) -> list[TextContent]:
        return await handle_tool(name, arguments or {})

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
