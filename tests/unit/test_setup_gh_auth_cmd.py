"""Tests for clade setup-gh-auth command."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from clade.cli.setup_gh_auth_cmd import setup_gh_auth_cmd


def _make_config(**overrides):
    from clade.cli.clade_config import BrotherEntry, CladeConfig

    brothers = overrides.pop("brothers", {
        "oppy": BrotherEntry(ssh="ian@masuda", role="worker"),
        "jerry": BrotherEntry(ssh="ian@cluster", role="worker"),
    })
    return CladeConfig(
        server_url="https://hearth.example.com",
        personal_name="doot",
        brothers=brothers,
        **overrides,
    )


class TestSetupGhAuth:
    @patch("clade.cli.setup_gh_auth_cmd.load_clade_config", return_value=None)
    def test_no_config(self, _):
        runner = CliRunner()
        result = runner.invoke(setup_gh_auth_cmd, ["oppy"], obj={})
        assert result.exit_code == 1
        assert "clade.yaml" in result.output

    @patch("clade.cli.setup_gh_auth_cmd.load_clade_config")
    def test_unknown_brother(self, mock_config):
        mock_config.return_value = _make_config()
        runner = CliRunner()
        result = runner.invoke(setup_gh_auth_cmd, ["unknown"], obj={})
        assert result.exit_code == 1
        assert "Unknown brother" in result.output
        assert "jerry" in result.output
        assert "oppy" in result.output

    @patch("clade.cli.setup_gh_auth_cmd.run_remote")
    @patch("clade.cli.setup_gh_auth_cmd.load_clade_config")
    def test_already_authenticated(self, mock_config, mock_remote):
        mock_config.return_value = _make_config()
        from clade.cli.ssh_utils import SSHResult

        # First call: check gh installed
        # Second call: check auth status
        mock_remote.side_effect = [
            SSHResult(success=True, stdout="/usr/bin/gh\nGH_FOUND"),
            SSHResult(success=True, stdout="Logged in to github.com as dunni3\nGH_AUTHED"),
        ]

        runner = CliRunner()
        result = runner.invoke(setup_gh_auth_cmd, ["oppy"], obj={})
        assert result.exit_code == 0
        assert "already authenticated" in result.output

    @patch("clade.cli.setup_gh_auth_cmd.run_remote")
    @patch("clade.cli.setup_gh_auth_cmd.load_clade_config")
    def test_ssh_failure(self, mock_config, mock_remote):
        mock_config.return_value = _make_config()
        from clade.cli.ssh_utils import SSHResult

        mock_remote.return_value = SSHResult(success=False, message="Connection refused")

        runner = CliRunner()
        result = runner.invoke(setup_gh_auth_cmd, ["oppy"], obj={})
        assert result.exit_code == 1
        assert "SSH" in result.output

    @patch("clade.cli.setup_gh_auth_cmd.run_remote")
    @patch("clade.cli.setup_gh_auth_cmd.load_clade_config")
    def test_install_and_authenticate(self, mock_config, mock_remote):
        mock_config.return_value = _make_config()
        from clade.cli.ssh_utils import SSHResult

        mock_remote.side_effect = [
            # 1. Check gh installed — not found
            SSHResult(success=True, stdout="GH_MISSING"),
            # 2. Install gh
            SSHResult(success=True, stdout="GH_INSTALL_OK"),
            # 3. Authenticate
            SSHResult(success=True, stdout="GH_AUTH_OK"),
            # 4. Verify
            SSHResult(success=True, stdout="Logged in to github.com as dunni3"),
        ]

        runner = CliRunner()
        result = runner.invoke(setup_gh_auth_cmd, ["oppy"], input="ghp_testtoken123\n", obj={})
        assert result.exit_code == 0
        assert "authenticated successfully" in result.output

    @patch("clade.cli.setup_gh_auth_cmd.run_remote")
    @patch("clade.cli.setup_gh_auth_cmd.load_clade_config")
    def test_install_failure(self, mock_config, mock_remote):
        mock_config.return_value = _make_config()
        from clade.cli.ssh_utils import SSHResult

        mock_remote.side_effect = [
            # 1. Check gh installed — not found
            SSHResult(success=True, stdout="GH_MISSING"),
            # 2. Install fails
            SSHResult(success=False, message="apt failed", stderr="E: Unable to locate package gh"),
        ]

        runner = CliRunner()
        result = runner.invoke(setup_gh_auth_cmd, ["oppy"], obj={})
        assert result.exit_code == 1
        assert "Failed to install" in result.output

    @patch("clade.cli.setup_gh_auth_cmd.run_remote")
    @patch("clade.cli.setup_gh_auth_cmd.load_clade_config")
    def test_auth_failure(self, mock_config, mock_remote):
        mock_config.return_value = _make_config()
        from clade.cli.ssh_utils import SSHResult

        mock_remote.side_effect = [
            # 1. Check gh installed — found
            SSHResult(success=True, stdout="/usr/bin/gh\nGH_FOUND"),
            # 2. Check auth — not authed
            SSHResult(success=True, stdout="GH_NOT_AUTHED"),
            # 3. Auth fails
            SSHResult(success=False, message="bad credentials", stderr="error: invalid token"),
        ]

        runner = CliRunner()
        result = runner.invoke(setup_gh_auth_cmd, ["oppy"], input="bad_token\n", obj={})
        assert result.exit_code == 1
        assert "Authentication failed" in result.output
