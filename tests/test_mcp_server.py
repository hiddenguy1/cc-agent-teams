"""Tests for MCP server tool handling (SQLite-based)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest

# Set env before importing mcp_server
os.environ["AGENT_TEAM_TEAM_NAME"] = "test-mcp-team"
os.environ["AGENT_TEAM_AGENT_NAME"] = "test-agent"
os.environ["AGENT_TEAM_AGENT_ROLE"] = "member"

from agent_team.mcp_server import handle_tool, _get_db  # noqa: E402

TEAM_NAME = "test-mcp-team"


@pytest.fixture(autouse=True)
def clean_env():
    import agent_team.mcp_server as srv
    srv._db = None
    team_dir = Path.home() / ".agent-team" / "teams" / TEAM_NAME
    if team_dir.exists():
        shutil.rmtree(team_dir)
    yield
    srv._db = None
    if team_dir.exists():
        shutil.rmtree(team_dir)


class TestMessageTools:
    @pytest.mark.asyncio
    async def test_send_message(self):
        with patch("agent_team.mcp_server.wake_agent"):
            result = await handle_tool("team_send_message", {
                "to": "backend", "content": "Hello",
            })
            assert "Message sent" in result[0].text

    @pytest.mark.asyncio
    async def test_get_messages_empty(self):
        result = await handle_tool("team_get_messages", {})
        assert "No new messages" in result[0].text

    @pytest.mark.asyncio
    async def test_get_messages_with_content(self):
        db = _get_db()
        db.send_message("leader", "test-agent", "Do this")
        result = await handle_tool("team_get_messages", {})
        assert "Do this" in result[0].text


class TestLockTools:
    @pytest.mark.asyncio
    async def test_acquire_lock_success(self):
        result = await handle_tool("team_acquire_lock", {"file_path": "src/main.py"})
        assert "Lock acquired" in result[0].text

    @pytest.mark.asyncio
    async def test_acquire_lock_failed(self):
        db = _get_db()
        db.acquire_lock("other-agent", "src/main.py")
        result = await handle_tool("team_acquire_lock", {"file_path": "src/main.py"})
        assert "locked by" in result[0].text

    @pytest.mark.asyncio
    async def test_release_lock(self):
        db = _get_db()
        db.acquire_lock("test-agent", "src/main.py")
        result = await handle_tool("team_release_lock", {"file_path": "src/main.py"})
        assert "Lock released" in result[0].text

    @pytest.mark.asyncio
    async def test_check_lock_locked(self):
        db = _get_db()
        db.acquire_lock("backend", "src/main.py")
        result = await handle_tool("team_check_lock", {"file_path": "src/main.py"})
        assert "Locked by backend" in result[0].text

    @pytest.mark.asyncio
    async def test_check_lock_free(self):
        result = await handle_tool("team_check_lock", {"file_path": "src/main.py"})
        assert "not locked" in result[0].text


class TestTaskTools:
    @pytest.mark.asyncio
    async def test_get_tasks(self):
        db = _get_db()
        db.create_task("Do work")
        result = await handle_tool("team_get_tasks", {"pending_only": True})
        assert "Do work" in result[0].text

    @pytest.mark.asyncio
    async def test_claim_task(self):
        db = _get_db()
        task = db.create_task("Do work")
        result = await handle_tool("team_claim_task", {"task_id": task["id"]})
        assert "claimed" in result[0].text

    @pytest.mark.asyncio
    async def test_report(self):
        db = _get_db()
        task = db.create_task("Do work")
        db.claim_task(task["id"], "test-agent")
        with patch("agent_team.mcp_server.wake_agent"):
            result = await handle_tool("team_report", {
                "task_id": task["id"], "summary": "Done!",
            })
            assert "Report sent" in result[0].text


class TestLeaderTools:
    @pytest.fixture(autouse=True)
    def set_leader_role(self):
        os.environ["AGENT_TEAM_AGENT_ROLE"] = "leader"
        os.environ["AGENT_TEAM_AGENT_NAME"] = "leader"
        import agent_team.mcp_server as srv
        srv.AGENT_NAME = "leader"
        srv.AGENT_ROLE = "leader"
        yield
        os.environ["AGENT_TEAM_AGENT_ROLE"] = "member"
        os.environ["AGENT_TEAM_AGENT_NAME"] = "test-agent"
        srv.AGENT_NAME = "test-agent"
        srv.AGENT_ROLE = "member"

    @pytest.mark.asyncio
    async def test_list_providers(self):
        with patch("agent_team.config.build_agent_config") as mock_config:
            from agent_team.models import AgentConfig, ProviderConfig
            mock_config.return_value = AgentConfig(
                providers={"kimi": ProviderConfig(name="Kimi", base_url="http://kimi", auth_token="", models={})},
                roles={},
            )
            result = await handle_tool("team_list_providers", {})
            assert "Kimi" in result[0].text

    @pytest.mark.asyncio
    async def test_create_task(self):
        result = await handle_tool("team_create_task", {
            "subject": "New task", "description": "Details",
        })
        assert "Task created" in result[0].text

    @pytest.mark.asyncio
    async def test_team_status(self):
        with patch("agent_team.config.load_team_config") as mock_cfg:
            mock_cfg.return_value = {"members": []}
            result = await handle_tool("team_status", {})
            assert TEAM_NAME in result[0].text
