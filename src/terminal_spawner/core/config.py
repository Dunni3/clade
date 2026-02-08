"""Configuration loading for terminal-spawner."""

import os
from pathlib import Path
from typing import Optional

import yaml

from .types import BrotherConfig, TerminalSpawnerConfig


# Hardcoded fallback configuration for backward compatibility
FALLBACK_CONFIG: TerminalSpawnerConfig = {
    "default_terminal_app": "terminal",
    "brothers": {
        "jerry": {
            "host": "cluster",
            "working_dir": None,
            "command": 'ssh -t cluster "bash -lc claude"',
            "description": "Brother Jerry — GPU jobs on the cluster",
        },
        "oppy": {
            "host": "masuda",
            "working_dir": "~/projects/mol_diffusion/OMTRA_oppy",
            "command": "ssh -t masuda \"bash -lc 'cd ~/projects/mol_diffusion/OMTRA_oppy && claude'\"",
            "description": "Brother Oppy — The architect on masuda",
        },
    },
    "mailbox": None,
}


def _find_config_file() -> Optional[Path]:
    """Search for config file in standard locations.

    Search order:
    1. ~/.config/terminal-spawner/config.yaml
    2. $XDG_CONFIG_HOME/terminal-spawner/config.yaml
    3. ~/.terminal-spawner.yaml

    Returns:
        Path to config file if found, None otherwise
    """
    # Check ~/.config/terminal-spawner/config.yaml
    config_dir = Path.home() / ".config" / "terminal-spawner"
    config_file = config_dir / "config.yaml"
    if config_file.exists():
        return config_file

    # Check XDG_CONFIG_HOME
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        config_file = Path(xdg_config) / "terminal-spawner" / "config.yaml"
        if config_file.exists():
            return config_file

    # Check ~/.terminal-spawner.yaml
    home_config = Path.home() / ".terminal-spawner.yaml"
    if home_config.exists():
        return home_config

    return None


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

        # Validate and build config
        config: TerminalSpawnerConfig = {
            "default_terminal_app": loaded.get("default_terminal_app", "terminal"),
            "brothers": loaded.get("brothers", {}),
            "mailbox": loaded.get("mailbox"),
        }

        # Generate commands for brothers if not provided
        for name, brother in config["brothers"].items():
            if "command" not in brother:
                brother["command"] = get_brother_command(brother)

        return config
    except Exception as e:
        # If config loading fails, warn and use fallback
        import warnings
        warnings.warn(
            f"Failed to load config from {config_path}: {e}. Using fallback configuration.",
            UserWarning,
        )
        return FALLBACK_CONFIG.copy()


def get_brother_command(brother: BrotherConfig) -> str:
    """Generate SSH command from brother configuration.

    Args:
        brother: Brother configuration dictionary

    Returns:
        SSH command string to connect to the brother
    """
    host = brother["host"]
    working_dir = brother.get("working_dir")

    if working_dir:
        # Need to cd to working dir first
        return f'ssh -t {host} "bash -lc \'cd {working_dir} && claude\'"'
    else:
        # Just launch claude
        return f'ssh -t {host} "bash -lc claude"'
