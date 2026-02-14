"""Tests for MCP utils (claude.json manipulation)."""

import json
from pathlib import Path

from clade.cli.mcp_utils import (
    is_mcp_registered,
    read_claude_json,
    register_mcp_server,
    write_claude_json,
)


class TestReadClaudeJson:
    def test_nonexistent(self, tmp_path: Path):
        result = read_claude_json(tmp_path / "missing.json")
        assert result == {}

    def test_valid(self, tmp_path: Path):
        p = tmp_path / "claude.json"
        p.write_text('{"mcpServers": {}}')
        result = read_claude_json(p)
        assert result == {"mcpServers": {}}

    def test_invalid_json(self, tmp_path: Path):
        p = tmp_path / "claude.json"
        p.write_text("not json")
        result = read_claude_json(p)
        assert result == {}


class TestWriteClaudeJson:
    def test_writes_json(self, tmp_path: Path):
        p = tmp_path / "claude.json"
        write_claude_json({"test": True}, p)
        assert p.exists()
        with open(p) as f:
            assert json.load(f) == {"test": True}

    def test_creates_parent_dirs(self, tmp_path: Path):
        p = tmp_path / "deep" / "nested" / "claude.json"
        write_claude_json({"test": True}, p)
        assert p.exists()


class TestRegisterMcpServer:
    def test_register_new(self, tmp_path: Path):
        p = tmp_path / "claude.json"
        register_mcp_server(
            "clade-worker",
            "/usr/bin/python3",
            "clade.mcp.server_lite",
            env={"HEARTH_URL": "https://example.com"},
            path=p,
        )
        data = read_claude_json(p)
        assert "clade-worker" in data["mcpServers"]
        srv = data["mcpServers"]["clade-worker"]
        assert srv["command"] == "/usr/bin/python3"
        assert srv["args"] == ["-m", "clade.mcp.server_lite"]
        assert srv["env"]["HEARTH_URL"] == "https://example.com"

    def test_preserves_existing_servers(self, tmp_path: Path):
        p = tmp_path / "claude.json"
        write_claude_json({"mcpServers": {"existing": {"command": "keep"}}}, p)
        register_mcp_server("new-server", "/usr/bin/python3", "some.module", path=p)
        data = read_claude_json(p)
        assert "existing" in data["mcpServers"]
        assert "new-server" in data["mcpServers"]

    def test_updates_existing_server(self, tmp_path: Path):
        p = tmp_path / "claude.json"
        register_mcp_server("srv", "/old/python", "old.module", path=p)
        register_mcp_server("srv", "/new/python", "new.module", path=p)
        data = read_claude_json(p)
        assert data["mcpServers"]["srv"]["command"] == "/new/python"

    def test_no_env(self, tmp_path: Path):
        p = tmp_path / "claude.json"
        register_mcp_server("srv", "/usr/bin/python3", "mod", path=p)
        data = read_claude_json(p)
        assert "env" not in data["mcpServers"]["srv"]


class TestIsMcpRegistered:
    def test_registered(self, tmp_path: Path):
        p = tmp_path / "claude.json"
        register_mcp_server("clade-worker", "/usr/bin/python3", "mod", path=p)
        assert is_mcp_registered("clade-worker", p)

    def test_not_registered(self, tmp_path: Path):
        p = tmp_path / "claude.json"
        assert not is_mcp_registered("clade-worker", p)

    def test_missing_file(self, tmp_path: Path):
        assert not is_mcp_registered("anything", tmp_path / "nope.json")
