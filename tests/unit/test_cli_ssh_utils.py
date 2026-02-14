"""Tests for CLI SSH utilities."""

from unittest.mock import MagicMock, patch

from clade.cli import ssh_utils
from clade.cli.ssh_utils import RemotePrereqs, SSHResult


class TestSSHResult:
    def test_defaults(self):
        r = SSHResult(success=True)
        assert r.success
        assert r.stdout == ""
        assert r.stderr == ""
        assert r.message == ""


class TestTestSSH:
    @patch("clade.cli.ssh_utils.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
        result = ssh_utils.test_ssh("ian@masuda")
        assert result.success
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "ian@masuda" in cmd
        assert "echo" in cmd

    @patch("clade.cli.ssh_utils.subprocess.run")
    def test_with_ssh_key(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
        ssh_utils.test_ssh("ian@masuda", ssh_key="~/.ssh/test.pem")
        cmd = mock_run.call_args[0][0]
        assert "-i" in cmd
        assert "~/.ssh/test.pem" in cmd

    @patch("clade.cli.ssh_utils.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=255, stdout="", stderr="Connection refused")
        result = ssh_utils.test_ssh("bad@host")
        assert not result.success

    @patch("clade.cli.ssh_utils.subprocess.run")
    def test_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ssh", timeout=10)
        result = ssh_utils.test_ssh("slow@host")
        assert not result.success
        assert "timed out" in result.message


class TestRunRemote:
    @patch("clade.cli.ssh_utils.subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="hello\n", stderr="")
        result = ssh_utils.run_remote("ian@masuda", "echo hello")
        assert result.success
        assert "hello" in result.stdout

    @patch("clade.cli.ssh_utils.subprocess.run")
    def test_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = ssh_utils.run_remote("ian@masuda", "bad-command")
        assert not result.success

    @patch("clade.cli.ssh_utils.subprocess.run")
    def test_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ssh", timeout=30)
        result = ssh_utils.run_remote("ian@masuda", "slow script", timeout=30)
        assert not result.success
        assert "timed out" in result.message


class TestRemotePrereqs:
    def test_all_ok(self):
        p = RemotePrereqs(python="/usr/bin/python3", python_version="3.12.0", claude=True, tmux=True, git=True)
        assert p.all_ok

    def test_missing_python(self):
        p = RemotePrereqs(python=None, claude=True, tmux=True, git=True)
        assert not p.all_ok

    def test_missing_claude(self):
        p = RemotePrereqs(python="/usr/bin/python3", claude=False, tmux=True, git=True)
        assert not p.all_ok


class TestCheckRemotePrereqs:
    @patch("clade.cli.ssh_utils.run_remote")
    def test_all_present(self, mock_run):
        mock_run.return_value = SSHResult(
            success=True,
            stdout="PYTHON:/usr/bin/python3.12:3.12.0\nCLAUDE:yes\nTMUX:yes\nGIT:yes\n",
        )
        prereqs = ssh_utils.check_remote_prereqs("ian@masuda")
        assert prereqs.all_ok
        assert prereqs.python == "/usr/bin/python3.12"
        assert prereqs.python_version == "3.12.0"
        assert prereqs.claude
        assert prereqs.tmux
        assert prereqs.git
        assert prereqs.errors == []

    @patch("clade.cli.ssh_utils.run_remote")
    def test_missing_claude(self, mock_run):
        mock_run.return_value = SSHResult(
            success=True,
            stdout="PYTHON:/usr/bin/python3:3.11.0\nCLAUDE:no\nTMUX:yes\nGIT:yes\n",
        )
        prereqs = ssh_utils.check_remote_prereqs("ian@masuda")
        assert not prereqs.all_ok
        assert not prereqs.claude
        assert "Claude Code not found" in prereqs.errors

    @patch("clade.cli.ssh_utils.run_remote")
    def test_ssh_failure(self, mock_run):
        mock_run.return_value = SSHResult(success=False, message="Connection refused")
        prereqs = ssh_utils.check_remote_prereqs("bad@host")
        assert not prereqs.all_ok
        assert len(prereqs.errors) > 0
