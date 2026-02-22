"""CladeConfig — data model and YAML persistence for clade.yaml."""

from __future__ import annotations

import json
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
    verify_ssl: bool = True
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


def build_brothers_registry(
    config: CladeConfig,
    keys: dict[str, str],
) -> dict[str, dict]:
    """Build brothers registry dict from clade config and API keys.

    Returns the same dict structure that brothers-ember.yaml would produce
    under its 'brothers' key. Only includes brothers with ember_host set.

    Args:
        config: Loaded CladeConfig.
        keys: Dict of brother names to API keys.

    Returns:
        Dict mapping brother names to config dicts with keys:
        ember_url, ember_api_key, hearth_api_key, and optionally working_dir.
    """
    registry: dict[str, dict] = {}

    for name, bro in config.brothers.items():
        if not bro.ember_host:
            continue

        api_key = keys.get(name, "")
        port = bro.ember_port or 8100
        entry: dict[str, str] = {
            "ember_url": f"http://{bro.ember_host}:{port}",
            "ember_api_key": api_key,
            "hearth_api_key": api_key,
        }
        if bro.working_dir:
            entry["working_dir"] = bro.working_dir
        registry[name] = entry

    return registry


def load_brothers_registry(config_dir: Path | None = None) -> dict[str, dict]:
    """Load brothers registry from clade.yaml + keys.json.

    Builds the registry at runtime from the source-of-truth config files,
    eliminating the need for a derived brothers-ember.yaml file.

    Args:
        config_dir: Override config directory. If None, uses default (~/.config/clade).

    Returns:
        Dict mapping brother names to config dicts, or empty dict if
        clade.yaml doesn't exist, has no Ember brothers, or keys.json is unreadable.
    """
    from .keys import load_keys, keys_path

    config = load_clade_config(default_config_path(config_dir))
    if config is None:
        return {}

    try:
        keys = load_keys(keys_path(config_dir))
    except (json.JSONDecodeError, OSError):
        keys = {}
    return build_brothers_registry(config, keys)


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
        verify_ssl=server_sec.get("verify_ssl", True),
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
    if config.server_url or config.server_ssh or config.server_ssh_key or not config.verify_ssl:
        server: dict = {}
        if config.server_url:
            server["url"] = config.server_url
        if config.server_ssh:
            server["ssh"] = config.server_ssh
        if config.server_ssh_key:
            server["ssh_key"] = config.server_ssh_key
        if not config.verify_ssl:
            server["verify_ssl"] = False
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
            brothers_data[name] = entry
        data["brothers"] = brothers_data

    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    return config_path
