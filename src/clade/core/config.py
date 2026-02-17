"""Configuration loading for the Clade."""

import os
from pathlib import Path
from typing import Optional

import yaml

from .types import BrotherConfig, TerminalSpawnerConfig


# Hardcoded fallback configuration for backward compatibility
FALLBACK_CONFIG: TerminalSpawnerConfig = {
    "brothers": {
        "jerry": {
            "host": "cluster",
            "working_dir": None,
            "description": "Brother Jerry — GPU jobs on the cluster",
        },
        "oppy": {
            "host": "masuda",
            "working_dir": "~/projects/mol_diffusion/OMTRA_oppy",
            "description": "Brother Oppy — The architect on masuda",
        },
    },
    "mailbox": None,
}


def _find_config_file() -> Optional[Path]:
    """Search for config file in standard locations.

    Search order (highest priority first):
    1. ~/.config/clade/clade.yaml  (new CLI format)
    2. $XDG_CONFIG_HOME/clade/clade.yaml
    3. ~/.config/clade/config.yaml (legacy format)
    4. $XDG_CONFIG_HOME/clade/config.yaml
    5. ~/.clade.yaml
    6. (fallback) ~/.config/terminal-spawner/config.yaml
    7. (fallback) ~/.terminal-spawner.yaml

    Returns:
        Path to config file if found, None otherwise
    """
    config_dir = Path.home() / ".config" / "clade"

    # Check clade.yaml (new CLI format) — highest priority
    clade_yaml = config_dir / "clade.yaml"
    if clade_yaml.exists():
        return clade_yaml

    # Check XDG clade.yaml
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        xdg_clade = Path(xdg_config) / "clade" / "clade.yaml"
        if xdg_clade.exists():
            return xdg_clade

    # Check config.yaml (legacy format)
    config_file = config_dir / "config.yaml"
    if config_file.exists():
        return config_file

    # Check XDG config.yaml
    if xdg_config:
        config_file = Path(xdg_config) / "clade" / "config.yaml"
        if config_file.exists():
            return config_file

    # Check ~/.clade.yaml
    home_config = Path.home() / ".clade.yaml"
    if home_config.exists():
        return home_config

    # Fallback: legacy terminal-spawner paths
    legacy_dir = Path.home() / ".config" / "terminal-spawner"
    legacy_file = legacy_dir / "config.yaml"
    if legacy_file.exists():
        return legacy_file

    legacy_home = Path.home() / ".terminal-spawner.yaml"
    if legacy_home.exists():
        return legacy_home

    return None


def _is_clade_yaml(loaded: dict) -> bool:
    """Detect whether a loaded YAML dict is in the new clade.yaml format."""
    return "clade" in loaded and isinstance(loaded["clade"], dict)


def _convert_clade_yaml(loaded: dict) -> TerminalSpawnerConfig:
    """Convert a clade.yaml dict to TerminalSpawnerConfig for MCP compatibility."""
    brothers: dict[str, BrotherConfig] = {}
    for name, bro in loaded.get("brothers", {}).items():
        ssh_str = bro.get("ssh", "")
        host = ssh_str.split("@")[-1] if "@" in ssh_str else ssh_str
        brother_dict: BrotherConfig = {
            "host": host,
            "working_dir": bro.get("working_dir"),
            "description": bro.get("description", ""),
        }
        brothers[name] = brother_dict

    server_sec = loaded.get("server", {})
    mailbox = None
    if server_sec.get("url"):
        mailbox = {"url": server_sec["url"]}

    return {
        "brothers": brothers,
        "mailbox": mailbox,
    }


def load_config(path: Optional[Path] = None) -> TerminalSpawnerConfig:
    """Load configuration from file or use fallback.

    Args:
        path: Optional explicit path to config file. If not provided,
              searches in standard locations.

    Returns:
        Configuration dictionary

    Note:
        If no config file is found, returns hardcoded fallback configuration
        for backward compatibility (jerry and oppy brothers).
    """
    # Use explicit path if provided, otherwise search
    config_path = path if path else _find_config_file()

    if config_path is None:
        # No config file found, use fallback
        return FALLBACK_CONFIG.copy()

    # Load YAML config
    try:
        with open(config_path) as f:
            loaded = yaml.safe_load(f)

        # Detect clade.yaml format (has 'clade:' top-level key)
        if isinstance(loaded, dict) and _is_clade_yaml(loaded):
            return _convert_clade_yaml(loaded)

        # Legacy config.yaml format
        config: TerminalSpawnerConfig = {
            "brothers": loaded.get("brothers", {}),
            "mailbox": loaded.get("mailbox"),
        }

        return config
    except Exception as e:
        # If config loading fails, warn and use fallback
        import warnings
        warnings.warn(
            f"Failed to load config from {config_path}: {e}. Using fallback configuration.",
            UserWarning,
        )
        return FALLBACK_CONFIG.copy()
