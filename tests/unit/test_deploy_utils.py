"""Tests for deploy_utils module."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from clade.cli.clade_config import CladeConfig
from clade.cli.deploy_utils import (
    deploy_clade_package,
    load_config_or_exit,
    require_server_ssh,
    scp_build_directory,
    scp_directory,
)


class TestLoadConfigOrExit:
    @patch("clade.cli.deploy_utils.load_clade_config")
    def test_returns_config(self, mock_load):
        config = CladeConfig(clade_name="Test")
        mock_load.return_value = config
        result = load_config_or_exit(None)
        assert result is config

    @patch("clade.cli.deploy_utils.load_clade_config")
    def test_exits_when_no_config(self, mock_load):
        mock_load.return_value = None
        with pytest.raises(SystemExit):
            load_config_or_exit(None)


class TestRequireServerSSH:
    def test_returns_host_and_key(self):
        config = CladeConfig(server_ssh="ubuntu@host", server_ssh_key="~/.ssh/key.pem")
        host, key = require_server_ssh(config)
        assert host == "ubuntu@host"
        assert key == "~/.ssh/key.pem"

    def test_returns_none_key_when_not_set(self):
        config = CladeConfig(server_ssh="ubuntu@host")
        host, key = require_server_ssh(config)
        assert host == "ubuntu@host"
        assert key is None

    def test_exits_when_no_ssh(self):
        config = CladeConfig()
        with pytest.raises(SystemExit):
            require_server_ssh(config)


class TestSCPDirectory:
    @patch("clade.cli.deploy_utils.subprocess.Popen")
    def test_success(self, mock_popen, tmp_path):
        src_dir = tmp_path / "mydir"
        src_dir.mkdir()
        (src_dir / "file.txt").write_text("hello")

        # Mock tar and ssh processes
        tar_mock = MagicMock()
        tar_mock.stdout = MagicMock()
        tar_mock.wait.return_value = 0

        ssh_mock = MagicMock()
        ssh_mock.communicate.return_value = (b"", b"")
        ssh_mock.returncode = 0

        mock_popen.side_effect = [tar_mock, ssh_mock]

        result = scp_directory(src_dir, "ubuntu@host", "/opt/dest")
        assert result.success

    def test_missing_dir(self):
        result = scp_directory("/nonexistent/dir", "ubuntu@host", "/opt/dest")
        assert not result.success
        assert "not found" in result.message

    @patch("clade.cli.deploy_utils.subprocess.Popen")
    def test_ssh_failure(self, mock_popen, tmp_path):
        src_dir = tmp_path / "mydir"
        src_dir.mkdir()
        (src_dir / "file.txt").write_text("hello")

        tar_mock = MagicMock()
        tar_mock.stdout = MagicMock()
        tar_mock.wait.return_value = 0

        ssh_mock = MagicMock()
        ssh_mock.communicate.return_value = (b"", b"Permission denied")
        ssh_mock.returncode = 1

        mock_popen.side_effect = [tar_mock, ssh_mock]

        result = scp_directory(src_dir, "ubuntu@host", "/opt/dest")
        assert not result.success

    @patch("clade.cli.deploy_utils.subprocess.Popen")
    def test_timeout(self, mock_popen, tmp_path):
        src_dir = tmp_path / "mydir"
        src_dir.mkdir()
        (src_dir / "file.txt").write_text("hello")

        tar_mock = MagicMock()
        tar_mock.stdout = MagicMock()
        tar_mock.kill = MagicMock()

        ssh_mock = MagicMock()
        ssh_mock.communicate.side_effect = subprocess.TimeoutExpired(cmd="ssh", timeout=60)
        ssh_mock.kill = MagicMock()

        mock_popen.side_effect = [tar_mock, ssh_mock]

        result = scp_directory(src_dir, "ubuntu@host", "/opt/dest", timeout=60)
        assert not result.success
        assert "timed out" in result.message


class TestSCPBuildDirectory:
    @patch("clade.cli.deploy_utils.subprocess.Popen")
    def test_success(self, mock_popen, tmp_path):
        src_dir = tmp_path / "dist"
        src_dir.mkdir()
        (src_dir / "index.html").write_text("<html>")

        tar_mock = MagicMock()
        tar_mock.stdout = MagicMock()
        tar_mock.wait.return_value = 0

        ssh_mock = MagicMock()
        ssh_mock.communicate.return_value = (b"SCP_BUILD_OK\n", b"")
        ssh_mock.returncode = 0

        mock_popen.side_effect = [tar_mock, ssh_mock]

        result = scp_build_directory(src_dir, "ubuntu@host", "/var/www/hearth")
        assert result.success

    def test_missing_dir(self):
        result = scp_build_directory("/nonexistent/dir", "ubuntu@host", "/var/www/hearth")
        assert not result.success
        assert "not found" in result.message

    @patch("clade.cli.deploy_utils.subprocess.Popen")
    def test_failure(self, mock_popen, tmp_path):
        src_dir = tmp_path / "dist"
        src_dir.mkdir()
        (src_dir / "index.html").write_text("<html>")

        tar_mock = MagicMock()
        tar_mock.stdout = MagicMock()
        tar_mock.wait.return_value = 0

        ssh_mock = MagicMock()
        ssh_mock.communicate.return_value = (b"", b"sudo: not found")
        ssh_mock.returncode = 1

        mock_popen.side_effect = [tar_mock, ssh_mock]

        result = scp_build_directory(src_dir, "ubuntu@host", "/var/www/hearth")
        assert not result.success


class TestDeployCladePackage:
    @patch("clade.cli.deploy_utils.run_remote")
    @patch("clade.cli.deploy_utils.subprocess.Popen")
    @patch("clade.cli.deploy_utils.Path")
    def test_success(self, mock_path_cls, mock_popen, mock_run_remote):
        # Mock project root with pyproject.toml
        mock_root = MagicMock()
        mock_root.parent = MagicMock()
        mock_root.name = "clade"
        (mock_root / "pyproject.toml").exists.return_value = True

        # __file__ resolution chain
        mock_file = MagicMock()
        mock_file.resolve.return_value.parent.parent.parent.parent = mock_root
        mock_path_cls.return_value = mock_file
        mock_path_cls.__truediv__ = Path.__truediv__

        # Mock tar + ssh transfer
        tar_mock = MagicMock()
        tar_mock.stdout = MagicMock()
        tar_mock.wait.return_value = 0

        ssh_mock = MagicMock()
        ssh_mock.communicate.return_value = (b"", b"")
        ssh_mock.returncode = 0

        mock_popen.side_effect = [tar_mock, ssh_mock]

        # Mock pip install
        mock_run_remote.return_value = MagicMock(
            success=True,
            stdout="Using pip: /usr/bin/pip\nDEPLOY_OK\n",
            stderr="",
            message="",
        )

        result = deploy_clade_package("ubuntu@host")
        assert result.success
        assert "DEPLOY_OK" in result.stdout

    @patch("clade.cli.deploy_utils.subprocess.Popen")
    def test_transfer_failure(self, mock_popen):
        # Mock tar + ssh transfer failure
        tar_mock = MagicMock()
        tar_mock.stdout = MagicMock()
        tar_mock.wait.return_value = 0

        ssh_mock = MagicMock()
        ssh_mock.communicate.return_value = (b"", b"Connection refused")
        ssh_mock.returncode = 1

        mock_popen.side_effect = [tar_mock, ssh_mock]

        result = deploy_clade_package("bad@host")
        assert not result.success
        assert "File transfer failed" in result.message

    @patch("clade.cli.deploy_utils.run_remote")
    @patch("clade.cli.deploy_utils.subprocess.Popen")
    def test_pip_failure(self, mock_popen, mock_run_remote):
        # Transfer succeeds
        tar_mock = MagicMock()
        tar_mock.stdout = MagicMock()
        tar_mock.wait.return_value = 0

        ssh_mock = MagicMock()
        ssh_mock.communicate.return_value = (b"", b"")
        ssh_mock.returncode = 0

        mock_popen.side_effect = [tar_mock, ssh_mock]

        # pip install fails
        mock_run_remote.return_value = MagicMock(
            success=False,
            stdout="ERROR: No pip found on remote",
            stderr="",
            message="Remote command failed",
        )

        result = deploy_clade_package("ubuntu@host")
        assert not result.success
