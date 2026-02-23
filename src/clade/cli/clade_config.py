"""CladeConfig — data model and YAML persistence for clade.yaml."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml


@dataclass
class BrotherEntry:
    """A brother definition in clade.yaml."""

    ssh: str
    working_dir: str | None = None
    role: str = "worker"
    description: str = ""
    personality: str = ""
    ember_port: int | None = None
    ember_host: str | None = None
    sudoers_configured: bool = False


@dataclass
class CladeConfig:
    """Top-level Clade configuration."""

    clade_name: str = "My Clade"
    created: str = ""
    personal_name: str = "doot"
    personal_description: str = "Personal assistant and coordinator"
    personal_personality: str = ""
    server_url: str | None = None
    server_ssh: str | None = None
    server_ssh_key: str | None = None
    brothers: dict[str, BrotherEntry] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.created:
            self.created = date.today().isoformat()


def default_config_path(config_dir: Path | None = None) -> Path:
    """Return the default path for clade.yaml.

    Args:
        config_dir: Override config directory. If None, uses ~/.config/clade.
    """
    if config_dir:
        return config_dir / "clade.yaml"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "clade" / "clade.yaml"
    return Path.home() / ".config" / "clade" / "clade.yaml"


def default_brothers_config_path(config_dir: Path | None = None) -> Path:
    """Return the default path for brothers-ember.yaml.

    Args:
        config_dir: Override config directory. If None, uses ~/.config/clade.
    """
    if config_dir:
        return config_dir / "brothers-ember.yaml"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "clade" / "brothers-ember.yaml"
    return Path.home() / ".config" / "clade" / "brothers-ember.yaml"


def load_clade_config(path: Path | None = None) -> CladeConfig | None:
    """Load a CladeConfig from YAML.

    Args:
        path: Path to clade.yaml. Uses default_config_path() if None.

    Returns:
        CladeConfig if the file exists and parses, None otherwise.
    """
    config_path = path or default_config_path()
    if not config_path.exists():
        return None

    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return None

    if not data or not isinstance(data, dict):
        return None

    clade_sec = data.get("clade", {})
    personal_sec = data.get("personal", {})
    server_sec = data.get("server", {})
    brothers_sec = data.get("brothers", {})

    brothers = {}
    for name, bro_data in brothers_sec.items():
        brothers[name] = BrotherEntry(
            ssh=bro_data.get("ssh", ""),
            working_dir=bro_data.get("working_dir"),
            role=bro_data.get("role", "worker"),
            description=bro_data.get("description", ""),
            personality=bro_data.get("personality", ""),
            ember_port=bro_data.get("ember_port"),
            ember_host=bro_data.get("ember_host"),
            sudoers_configured=bro_data.get("sudoers_configured", False),
        )

    return CladeConfig(
        clade_name=clade_sec.get("name", "My Clade"),
        created=clade_sec.get("created", ""),
        personal_name=personal_sec.get("name", "doot"),
        personal_description=personal_sec.get("description", ""),
        personal_personality=personal_sec.get("personality", ""),
        server_url=server_sec.get("url"),
        server_ssh=server_sec.get("ssh"),
        server_ssh_key=server_sec.get("ssh_key"),
        brothers=brothers,
    )


def save_clade_config(config: CladeConfig, path: Path | None = None) -> Path:
    """Save a CladeConfig to YAML.

    Args:
        config: The configuration to save.
        path: Where to write. Uses default_config_path() if None.

    Returns:
        The path written to.
    """
    config_path = path or default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {
        "clade": {
            "name": config.clade_name,
            "created": config.created,
        },
        "personal": {
            "name": config.personal_name,
            "description": config.personal_description,
        },
    }
    if config.personal_personality:
        data["personal"]["personality"] = config.personal_personality

    # Only include server section if any server field is set
    if config.server_url or config.server_ssh or config.server_ssh_key:
        server: dict = {}
        if config.server_url:
            server["url"] = config.server_url
        if config.server_ssh:
            server["ssh"] = config.server_ssh
        if config.server_ssh_key:
            server["ssh_key"] = config.server_ssh_key
        data["server"] = server

    # Brothers
    if config.brothers:
        brothers_data: dict = {}
        for name, bro in config.brothers.items():
            entry: dict = {"ssh": bro.ssh}
            if bro.working_dir:
                entry["working_dir"] = bro.working_dir
            entry["role"] = bro.role
            if bro.description:
                entry["description"] = bro.description
            if bro.personality:
                entry["personality"] = bro.personality
            if bro.ember_port is not None:
                entry["ember_port"] = bro.ember_port
            if bro.ember_host is not None:
                entry["ember_host"] = bro.ember_host
            if bro.sudoers_configured:
                entry["sudoers_configured"] = True
            brothers_data[name] = entry
        data["brothers"] = brothers_data

    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    return config_path
