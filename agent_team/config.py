"""Configuration loading for Agent Team."""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

from agent_team.models import AgentConfig, ProviderConfig, RoleConfig


def _config_dir() -> Path:
    return Path(__file__).parent.parent / "config"


def _expand_env_vars(data: dict | list | str | Any) -> Any:
    """Recursively expand ${VAR} and ${VAR:-default} in YAML data."""
    import re

    if isinstance(data, str):
        def replacer(match):
            key = match.group(1)
            default = match.group(2)
            return os.environ.get(key, default if default is not None else match.group(0))
        return re.sub(r'\$\{([^}:-]+)(?::-([^}]*))?\}', replacer, data)
    elif isinstance(data, dict):
        return {k: _expand_env_vars(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_expand_env_vars(item) for item in data]
    return data


def load_providers() -> dict:
    """Load provider configurations from config/providers.yaml."""
    path = _config_dir() / "providers.yaml"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return _expand_env_vars(data)


def load_roles() -> dict:
    """Load role templates from config/roles.yaml."""
    path = _config_dir() / "roles.yaml"
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_agent_config() -> AgentConfig:
    """Build full config from providers.yaml + roles.yaml."""
    providers_data = load_providers()
    roles_data = load_roles()

    providers: dict[str, ProviderConfig] = {}
    for key, val in providers_data.get("providers", {}).items():
        providers[key] = ProviderConfig(
            name=val.get("name", key),
            base_url=val.get("base_url", ""),
            auth_token=val.get("auth_token", ""),
            models=val.get("models", {}),
        )

    roles: dict[str, RoleConfig] = {}
    for key, val in roles_data.get("roles", {}).items():
        roles[key] = RoleConfig(
            name=val.get("name", key),
            description=val.get("description", ""),
            default_provider=val.get("default_provider", ""),
            default_model=val.get("default_model", ""),
        )

    return AgentConfig(providers=providers, roles=roles)


def generate_env_for_member(provider_key: str, model_key: str, providers: dict[str, ProviderConfig]) -> dict[str, str]:
    """Generate environment variables for a team member based on provider config."""
    provider = providers.get(provider_key)
    if provider is None:
        return {}
    models = provider.models
    model = models.get(model_key, {})
    model_name = model.get("name", model_key) if isinstance(model, dict) else model_key

    env = {
        "ANTHROPIC_BASE_URL": provider.base_url,
        "ANTHROPIC_AUTH_TOKEN": provider.auth_token,
        "ANTHROPIC_MODEL": model_name,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": model_name,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": model_name,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": model_name,
    }

    # Override with model-specific aliases if defined
    if isinstance(model, dict):
        for alias, alias_model in model.get("aliases", {}).items():
            alias_upper = alias.upper()
            env[f"ANTHROPIC_DEFAULT_{alias_upper}_MODEL"] = alias_model

    return env


def save_team_config(team_name: str, config: dict) -> Path:
    """Save team configuration to ~/.agent-team/teams/{team}/config.json."""
    team_dir = Path.home() / ".agent-team" / "teams" / team_name
    team_dir.mkdir(parents=True, exist_ok=True)
    config_path = team_dir / "config.json"
    with config_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    return config_path


def load_team_config(team_name: str) -> dict:
    """Load team configuration from disk."""
    config_path = Path.home() / ".agent-team" / "teams" / team_name / "config.json"
    if not config_path.exists():
        return {}
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)
