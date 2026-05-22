"""Tests for configuration loading."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_team.config import (
    _expand_env_vars,
    build_agent_config,
    generate_env_for_member,
    load_providers,
    load_roles,
    load_team_config,
    save_team_config,
)
from agent_team.models import AgentConfig, ProviderConfig, RoleConfig


class TestExpandEnvVars:
    def test_no_placeholder(self):
        assert _expand_env_vars("hello") == "hello"

    def test_existing_env_var(self, monkeypatch):
        monkeypatch.setenv("MY_VAR", "world")
        assert _expand_env_vars("hello ${MY_VAR}") == "hello world"

    def test_missing_env_var(self):
        assert _expand_env_vars("hello ${MISSING_VAR}") == "hello ${MISSING_VAR}"

    def test_default_value(self):
        assert _expand_env_vars("hello ${MISSING:-default}") == "hello default"

    def test_dict_expansion(self, monkeypatch):
        monkeypatch.setenv("URL", "http://api")
        data = {"base_url": "${URL}", "name": "test"}
        result = _expand_env_vars(data)
        assert result["base_url"] == "http://api"
        assert result["name"] == "test"

    def test_list_expansion(self, monkeypatch):
        monkeypatch.setenv("TOKEN", "abc123")
        data = ["${TOKEN}", "static"]
        assert _expand_env_vars(data) == ["abc123", "static"]

    def test_nested_structure(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "secret")
        data = {"providers": {"p1": {"auth_token": "${API_KEY}"}}}
        result = _expand_env_vars(data)
        assert result["providers"]["p1"]["auth_token"] == "secret"


class TestLoadProviders:
    def test_load_from_real_file(self):
        providers = load_providers()
        assert "providers" in providers
        # Should contain at least kimi provider
        assert "kimi" in providers["providers"]
        kimi = providers["providers"]["kimi"]
        assert "base_url" in kimi
        assert "models" in kimi

    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "agent_team.config._config_dir", lambda: tmp_path
        )
        assert load_providers() == {}


class TestLoadRoles:
    def test_load_from_real_file(self):
        roles = load_roles()
        assert "roles" in roles
        assert "backend" in roles["roles"]
        backend = roles["roles"]["backend"]
        assert backend["name"] == "后端开发"
        assert "kimi" in backend["default_provider"]

    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "agent_team.config._config_dir", lambda: tmp_path
        )
        assert load_roles() == {}


class TestBuildAgentConfig:
    def test_builds_config(self):
        config = build_agent_config()
        assert isinstance(config, AgentConfig)
        assert "kimi" in config.providers
        assert "backend" in config.roles

        provider = config.providers["kimi"]
        assert isinstance(provider, ProviderConfig)
        assert provider.base_url != ""

        role = config.roles["backend"]
        assert isinstance(role, RoleConfig)
        assert role.default_provider == "kimi"


class TestGenerateEnvForMember:
    def test_generates_env(self):
        providers = {
            "kimi": ProviderConfig(
                name="Kimi",
                base_url="https://api.kimi.com",
                auth_token="test-token",
                models={
                    "kimi-for-coding": {
                        "name": "kimi-for-coding",
                    }
                },
            )
        }
        env = generate_env_for_member("kimi", "kimi-for-coding", providers)
        assert env["ANTHROPIC_BASE_URL"] == "https://api.kimi.com"
        assert env["ANTHROPIC_AUTH_TOKEN"] == "test-token"
        assert env["ANTHROPIC_MODEL"] == "kimi-for-coding"

    def test_with_aliases(self):
        providers = {
            "deepseek": ProviderConfig(
                name="DeepSeek",
                base_url="https://api.deepseek.com",
                auth_token="token",
                models={
                    "deepseek-v4-pro": {
                        "name": "deepseek-v4-pro",
                        "aliases": {
                            "sonnet": "deepseek-v4-pro",
                            "opus": "deepseek-v4-pro",
                        }
                    }
                },
            )
        }
        env = generate_env_for_member("deepseek", "deepseek-v4-pro", providers)
        assert env["ANTHROPIC_DEFAULT_SONNET_MODEL"] == "deepseek-v4-pro"
        assert env["ANTHROPIC_DEFAULT_OPUS_MODEL"] == "deepseek-v4-pro"

    def test_missing_provider(self):
        env = generate_env_for_member("missing", "model", {})
        assert env == {}


class TestTeamConfig:
    TEAM = "test-config-team"

    @pytest.fixture(autouse=True)
    def clean_team_dir(self):
        team_dir = Path.home() / ".agent-team" / "teams" / self.TEAM
        if team_dir.exists():
            import shutil
            shutil.rmtree(team_dir)
        yield
        if team_dir.exists():
            import shutil
            shutil.rmtree(team_dir)

    def test_save_and_load(self):
        config = {"name": self.TEAM, "members": [{"name": "backend", "role": "backend"}]}
        path = save_team_config(self.TEAM, config)
        assert path.exists()

        loaded = load_team_config(self.TEAM)
        assert loaded["name"] == self.TEAM
        assert loaded["members"][0]["name"] == "backend"

    def test_load_missing(self):
        loaded = load_team_config("nonexistent-team-12345")
        assert loaded == {}
