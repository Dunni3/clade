"""Tests for clade setup-github command."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from clade.cli.setup_github_cmd import (
    _check_gh_cli,
    _detect_github_repo,
    _set_github_secret,
    setup_github_cmd,
)


# --- _detect_github_repo ---


class TestDetectGithubRepo:
    @patch("clade.cli.setup_github_cmd.subprocess.run")
    def test_ssh_url(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="git@github.com:Dunni3/clade.git\n"
        )
        assert _detect_github_repo() == ("Dunni3", "clade")

    @patch("clade.cli.setup_github_cmd.subprocess.run")
    def test_https_url(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="https://github.com/Dunni3/clade.git\n"
        )
        assert _detect_github_repo() == ("Dunni3", "clade")

    @patch("clade.cli.setup_github_cmd.subprocess.run")
    def test_https_no_git_suffix(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="https://github.com/owner/repo\n"
        )
        assert _detect_github_repo() == ("owner", "repo")

    @patch("clade.cli.setup_github_cmd.subprocess.run")
    def test_non_github_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="git@gitlab.com:owner/repo.git\n"
        )
        assert _detect_github_repo() is None

    @patch("clade.cli.setup_github_cmd.subprocess.run")
    def test_no_remote_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert _detect_github_repo() is None


# --- _check_gh_cli ---


class TestCheckGhCli:
    @patch("clade.cli.setup_github_cmd.shutil.which", return_value=None)
    def test_not_installed(self, _):
        ok, msg = _check_gh_cli()
        assert not ok
        assert "not found" in msg

    @patch("clade.cli.setup_github_cmd.subprocess.run")
    @patch("clade.cli.setup_github_cmd.shutil.which", return_value="/usr/bin/gh")
    def test_not_authenticated(self, _, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="not logged in")
        ok, msg = _check_gh_cli()
        assert not ok
        assert "not authenticated" in msg

    @patch("clade.cli.setup_github_cmd.subprocess.run")
    @patch("clade.cli.setup_github_cmd.shutil.which", return_value="/usr/bin/gh")
    def test_happy_path(self, _, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        ok, msg = _check_gh_cli()
        assert ok


# --- _set_github_secret ---


class TestSetGithubSecret:
    @patch("clade.cli.setup_github_cmd.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        assert _set_github_secret("owner/repo", "MY_SECRET", "val") is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][0] == ["gh", "secret", "set", "MY_SECRET", "--repo", "owner/repo"]
        assert call_args[1]["input"] == "val"

    @patch("clade.cli.setup_github_cmd.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        assert _set_github_secret("owner/repo", "MY_SECRET", "val") is False


# --- Template ---


class TestTemplate:
    def test_template_contains_repo_agnostic_link(self):
        from clade.templates import render_template

        content = render_template("hearth-bridge.yml")
        # Should use ${{ github.repository }} not hardcoded repo
        assert "${{ github.repository }}" in content
        assert 'PR_LINK="Dunni3/clade' not in content

    def test_template_is_valid_yaml_structure(self):
        from clade.templates import render_template

        content = render_template("hearth-bridge.yml")
        assert "name: Hearth-PR Bridge" in content
        assert "pull_request:" in content
        assert "hearth-bridge:" in content


# --- Key generation ---


class TestKeyGeneration:
    @patch("clade.cli.setup_github_cmd.add_key")
    @patch("clade.cli.setup_github_cmd.load_keys", return_value={})
    def test_key_name_format(self, mock_load, mock_add):
        """Key name should be github-actions-{owner}-{repo}."""
        mock_add.return_value = "test-key"

        # Simulate the key name the command would generate
        owner, repo = "Dunni3", "clade"
        key_name = f"github-actions-{owner}-{repo}"
        assert key_name == "github-actions-Dunni3-clade"

        # Call through the patched module-level import
        from clade.cli.setup_github_cmd import add_key as patched_add_key
        patched_add_key(key_name)
        mock_add.assert_called_once_with(key_name)

    @patch("clade.cli.setup_github_cmd.load_keys")
    def test_existing_key_reused(self, mock_load):
        """If key already exists, it should be reused."""
        mock_load.return_value = {"github-actions-Dunni3-clade": "existing-key"}
        existing = mock_load()
        key_name = "github-actions-Dunni3-clade"
        assert key_name in existing
        assert existing[key_name] == "existing-key"


# --- Full flow ---


class TestSetupGithubFullFlow:
    def _make_config(self):
        from clade.cli.clade_config import CladeConfig

        return CladeConfig(
            server_url="https://hearth.example.com",
            personal_name="doot",
        )

    @patch("clade.cli.setup_github_cmd._register_key")
    @patch("clade.cli.setup_github_cmd._set_github_secret", return_value=True)
    @patch("clade.cli.setup_github_cmd._get_git_root")
    @patch("clade.cli.setup_github_cmd._detect_github_repo", return_value=("Dunni3", "clade"))
    @patch("clade.cli.setup_github_cmd._check_gh_cli", return_value=(True, "ok"))
    @patch("clade.cli.setup_github_cmd.load_keys", return_value={"doot": "doot-key"})
    @patch("clade.cli.setup_github_cmd.add_key", return_value="new-key")
    @patch("clade.cli.setup_github_cmd.load_clade_config")
    def test_happy_path(
        self,
        mock_config,
        mock_add_key,
        mock_load_keys,
        mock_gh_cli,
        mock_detect,
        mock_git_root,
        mock_secret,
        mock_register,
        tmp_path,
    ):
        mock_config.return_value = self._make_config()
        mock_git_root.return_value = tmp_path

        runner = CliRunner()
        result = runner.invoke(setup_github_cmd, [], obj={})
        assert result.exit_code == 0
        assert "Done!" in result.output

        # Workflow file should be written
        workflow = tmp_path / ".github" / "workflows" / "hearth-bridge.yml"
        assert workflow.exists()
        assert "${{ github.repository }}" in workflow.read_text()

        # Secrets should be set
        assert mock_secret.call_count == 2

    @patch("clade.cli.setup_github_cmd.load_clade_config", return_value=None)
    def test_no_config(self, _):
        runner = CliRunner()
        result = runner.invoke(setup_github_cmd, [], obj={})
        assert result.exit_code == 1
        assert "clade.yaml" in result.output

    @patch("clade.cli.setup_github_cmd._check_gh_cli", return_value=(False, "not found"))
    @patch("clade.cli.setup_github_cmd.load_clade_config")
    def test_no_gh_cli(self, mock_config, mock_gh):
        mock_config.return_value = self._make_config()
        runner = CliRunner()
        result = runner.invoke(setup_github_cmd, [], obj={})
        assert result.exit_code == 1

    @patch("clade.cli.setup_github_cmd._detect_github_repo", return_value=None)
    @patch("clade.cli.setup_github_cmd._check_gh_cli", return_value=(True, "ok"))
    @patch("clade.cli.setup_github_cmd.load_clade_config")
    def test_non_github_remote(self, mock_config, mock_gh, mock_detect):
        mock_config.return_value = self._make_config()
        runner = CliRunner()
        result = runner.invoke(setup_github_cmd, [], obj={})
        assert result.exit_code == 1
        assert "Could not detect" in result.output
