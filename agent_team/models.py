"""Pydantic data models for Agent Team."""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    message = "message"
    broadcast = "broadcast"
    report = "report"
    lock_acquire = "lock_acquire"
    lock_release = "lock_release"


class TaskStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    blocked = "blocked"


class TeamMessage(BaseModel):
    id: str = Field(default_factory=lambda: f"msg-{uuid.uuid4().hex[:12]}")
    timestamp: float = Field(default_factory=time.time)
    from_agent: str
    to: str  # "all" | "leader" | specific agent name
    type: MessageType = MessageType.message
    content: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class FileLock(BaseModel):
    agent: str
    acquired_at: float
    task_id: str = ""


class LockEvent(BaseModel):
    timestamp: float = Field(default_factory=time.time)
    agent: str
    action: str  # "acquire" | "release"
    file: str
    task_id: str = ""


class Task(BaseModel):
    id: str = Field(default_factory=lambda: f"task-{uuid.uuid4().hex[:8]}")
    subject: str
    description: str = ""
    owner: str | None = None  # agent name or null
    status: TaskStatus = TaskStatus.pending
    created_at: float = Field(default_factory=time.time)
    completed_at: float | None = None
    blocked_by: list[str] = Field(default_factory=list)


class TeamMember(BaseModel):
    name: str
    role: str
    provider: str
    model: str
    status: str = "idle"  # idle | working | error
    current_task: str | None = None


class TeamStatus(BaseModel):
    name: str
    members: list[TeamMember]
    locks: dict[str, FileLock]
    tasks: list[Task]
    unread_reports: int = 0


class ProviderConfig(BaseModel):
    name: str
    base_url: str
    auth_token: str
    models: dict[str, dict[str, Any]]


class RoleConfig(BaseModel):
    name: str
    description: str
    default_provider: str
    default_model: str


class AgentConfig(BaseModel):
    providers: dict[str, ProviderConfig]
    roles: dict[str, RoleConfig]
