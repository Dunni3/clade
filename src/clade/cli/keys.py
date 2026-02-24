"""API key generation and secure storage for Clade brothers."""

from __future__ import annotations

import json
import os
import secrets
import stat
from pathlib import Path


def generate_api_key() -> str:
    """Generate a secure random API key."""
    return secrets.token_urlsafe(32)


def keys_path(config_dir: Path | None = None) -> Path:
    """Return the default path for keys.json.

    Args:
        config_dir: Override config directory. If None, uses ~/.config/clade.
    """
    if config_dir:
        return config_dir / "keys.json"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "clade" / "keys.json"
    return Path.home() / ".config" / "clade" / "keys.json"


def load_keys(path: Path | None = None) -> dict[str, str]:
    """Load API keys from JSON file.

    Args:
        path: Path to keys file. Uses keys_path() if None.

    Returns:
        Dict mapping brother names to API keys.
    """
    kp = path or keys_path()
    if not kp.exists():
        return {}
    with open(kp) as f:
        return json.load(f)


def save_keys(keys: dict[str, str], path: Path | None = None) -> Path:
    """Save API keys to JSON file with restricted permissions (0600).

    Args:
        keys: Dict mapping brother names to API keys.
        path: Where to write. Uses keys_path() if None.

    Returns:
        The path written to.
    """
    kp = path or keys_path()
    kp.parent.mkdir(parents=True, exist_ok=True)
    with open(kp, "w") as f:
        json.dump(keys, f, indent=2)
    os.chmod(kp, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    return kp


def add_key(name: str, path: Path | None = None, force: bool = False) -> str:
    """Generate an API key for a brother and save it.

    Idempotent: if a key already exists for *name*, returns it unchanged
    unless *force* is True.

    Args:
        name: Brother name.
        path: Path to keys file.
        force: Generate a new key even if one already exists.

    Returns:
        The API key (existing or newly generated).
    """
    keys = load_keys(path)
    if not force and name in keys:
        return keys[name]
    key = generate_api_key()
    keys[name] = key
    save_keys(keys, path)
    return key


def merge_keys_into_registry(registry: dict[str, dict], keys: dict[str, str]) -> None:
    """Merge API keys from keys dict into a brothers/workers registry (in-place).

    For each entry in *registry* whose name appears in *keys*, sets
    ``ember_api_key`` and ``hearth_api_key`` to the corresponding key value.

    Args:
        registry: Dict of brother/worker names to config dicts.
        keys: Dict of names to API keys.
    """
    for name, entry in registry.items():
        if name in keys:
            entry["ember_api_key"] = keys[name]
            entry["hearth_api_key"] = keys[name]


def format_api_keys_env(keys: dict[str, str]) -> str:
    """Format keys dict as a systemd-compatible env value.

    Returns:
        String like "key1:name1,key2:name2" for use in MAILBOX_API_KEYS env var.
    """
    return ",".join(f"{key}:{name}" for name, key in keys.items())
