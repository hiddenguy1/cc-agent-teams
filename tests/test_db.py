"""Tests for SQLite storage layer (TeamDB)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agent_team.db import TeamDB

TEAM_NAME = "test-db-team"


@pytest.fixture(autouse=True)
def clean_team_dir():
    team_dir = Path.home() / ".agent-team" / "teams" / TEAM_NAME
    if team_dir.exists():
        shutil.rmtree(team_dir)
    yield
    if team_dir.exists():
        shutil.rmtree(team_dir)


class TestMessages:
    def test_send_and_get(self):
        db = TeamDB(TEAM_NAME)
        db.send_message("leader", "backend", "Hello")
        messages = db.get_messages("backend")
        assert len(messages) == 1
        assert messages[0]["content"] == "Hello"
        assert messages[0]["from_agent"] == "leader"
        db.close()

    def test_broadcast_visible_to_all(self):
        db = TeamDB(TEAM_NAME)
        db.send_message("leader", "all", "Broadcast!")
        assert len(db.get_messages("backend")) == 1
        assert len(db.get_messages("frontend")) == 1
        db.close()

    def test_broadcast_not_visible_to_sender(self):
        db = TeamDB(TEAM_NAME)
        db.send_message("backend", "all", "Hey all")
        assert len(db.get_messages("backend")) == 0
        assert len(db.get_messages("frontend")) == 1
        db.close()

    def test_unread_only(self):
        db = TeamDB(TEAM_NAME)
        db.send_message("leader", "backend", "msg1")
        db.send_message("leader", "backend", "msg2")
        msgs = db.get_messages("backend", unread_only=True)
        assert len(msgs) == 2
        db.mark_read("backend", [msgs[0]["id"]])
        msgs2 = db.get_messages("backend", unread_only=True)
        assert len(msgs2) == 1
        assert msgs2[0]["content"] == "msg2"
        db.close()

    def test_unread_count(self):
        db = TeamDB(TEAM_NAME)
        assert db.get_unread_count("backend") == 0
        db.send_message("leader", "backend", "x")
        assert db.get_unread_count("backend") == 1
        db.close()

    def test_limit(self):
        db = TeamDB(TEAM_NAME)
        for i in range(10):
            db.send_message("leader", "backend", f"msg{i}")
        msgs = db.get_messages("backend", limit=3)
        assert len(msgs) == 3
        assert msgs[-1]["content"] == "msg9"
        db.close()

    def test_multiple_recipients(self):
        db = TeamDB(TEAM_NAME)
        db.send_message("leader", "backend", "B")
        db.send_message("leader", "frontend", "F")
        assert len(db.get_messages("backend")) == 1
        assert len(db.get_messages("frontend")) == 1
        db.close()


class TestLocks:
    def test_acquire_success(self):
        db = TeamDB(TEAM_NAME)
        assert db.acquire_lock("backend", "src/main.py") is True
        db.close()

    def test_acquire_already_locked(self):
        db = TeamDB(TEAM_NAME)
        db.acquire_lock("backend", "src/main.py")
        assert db.acquire_lock("frontend", "src/main.py") is False
        db.close()

    def test_release_success(self):
        db = TeamDB(TEAM_NAME)
        db.acquire_lock("backend", "src/main.py")
        assert db.release_lock("backend", "src/main.py") is True
        db.close()

    def test_release_wrong_agent(self):
        db = TeamDB(TEAM_NAME)
        db.acquire_lock("backend", "src/main.py")
        assert db.release_lock("frontend", "src/main.py") is False
        db.close()

    def test_check_lock(self):
        db = TeamDB(TEAM_NAME)
        db.acquire_lock("backend", "src/main.py")
        lock = db.check_lock("src/main.py")
        assert lock is not None
        assert lock["agent"] == "backend"
        db.close()

    def test_check_free(self):
        db = TeamDB(TEAM_NAME)
        assert db.check_lock("src/main.py") is None
        db.close()

    def test_release_all(self):
        db = TeamDB(TEAM_NAME)
        db.acquire_lock("backend", "a.py")
        db.acquire_lock("backend", "b.py")
        db.acquire_lock("frontend", "c.py")
        released = db.release_all_locks("backend")
        assert sorted(released) == ["a.py", "b.py"]
        assert db.check_lock("c.py") is not None
        db.close()


class TestTasks:
    def test_create_task(self):
        db = TeamDB(TEAM_NAME)
        task = db.create_task("Implement auth", "Add JWT")
        assert task["subject"] == "Implement auth"
        assert task["status"] == "pending"
        assert task["owner"] is None
        db.close()

    def test_claim_success(self):
        db = TeamDB(TEAM_NAME)
        task = db.create_task("Do work")
        assert db.claim_task(task["id"], "backend") is True
        tasks = db.get_tasks()
        assert tasks[0]["owner"] == "backend"
        assert tasks[0]["status"] == "in_progress"
        db.close()

    def test_claim_already_owned(self):
        db = TeamDB(TEAM_NAME)
        task = db.create_task("Do work")
        db.claim_task(task["id"], "backend")
        assert db.claim_task(task["id"], "frontend") is False
        db.close()

    def test_complete(self):
        db = TeamDB(TEAM_NAME)
        task = db.create_task("Do work")
        db.claim_task(task["id"], "backend")
        assert db.complete_task(task["id"], "backend") is True
        tasks = db.get_tasks()
        assert tasks[0]["status"] == "completed"
        db.close()

    def test_get_pending_only(self):
        db = TeamDB(TEAM_NAME)
        t1 = db.create_task("Pending")
        t2 = db.create_task("Claimed")
        db.claim_task(t2["id"], "backend")
        pending = db.get_tasks(pending_only=True)
        assert len(pending) == 1
        assert pending[0]["id"] == t1["id"]
        db.close()
