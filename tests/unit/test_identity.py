"""Tests for identity section generation and CLAUDE.md management."""

from pathlib import Path
from unittest.mock import patch

from clade.cli.identity import (
    MARKER_END,
    MARKER_START,
    generate_conductor_identity,
    generate_personal_identity,
    generate_worker_identity,
    upsert_identity_section,
    write_identity_local,
    write_identity_remote,
)
from clade.cli.ssh_utils import SSHResult


class TestGeneratePersonalIdentity:
    def test_basic(self):
        result = generate_personal_identity("doot", "The Clade")
        assert MARKER_START in result
        assert MARKER_END in result
        assert "**Name:** doot" in result
        assert "**Role:** Personal coordinator" in result
        assert "clade-personal" in result
        assert "No personality description provided." in result

    def test_with_personality(self):
        result = generate_personal_identity(
            "doot", "The Clade", personality="Methodical and detail-oriented"
        )
        assert "Methodical and detail-oriented" in result
        assert "No personality description provided." not in result

    def test_with_brothers(self):
        brothers = {
            "oppy": {"role": "worker", "description": "The architect"},
            "jerry": {"role": "worker", "description": "The runner"},
        }
        result = generate_personal_identity("doot", "The Clade", brothers=brothers)
        assert "## Brothers" in result
        assert "**oppy**" in result
        assert "The architect" in result
        assert "**jerry**" in result

    def test_without_brothers(self):
        result = generate_personal_identity("doot", "The Clade")
        assert "## Brothers" not in result

    def test_tools_listed(self):
        result = generate_personal_identity("doot", "The Clade")
        assert "spawn_terminal" in result
        assert "connect_to_brother" in result
        assert "initiate_ssh_task" in result
        assert "send_message" in result


class TestGenerateConductorIdentity:
    def test_basic(self):
        result = generate_conductor_identity("kamaji", "The Clade")
        assert MARKER_START in result
        assert MARKER_END in result
        assert "**Name:** kamaji" in result
        assert "**Role:** Conductor" in result
        assert "clade-conductor" in result

    def test_with_personality(self):
        result = generate_conductor_identity(
            "kamaji", "The Clade",
            personality="Gruff and no-nonsense but quietly kind"
        )
        assert "Gruff and no-nonsense" in result

    def test_conductor_tools_listed(self):
        result = generate_conductor_identity("kamaji", "The Clade")
        assert "delegate_task" in result
        assert "check_worker_health" in result
        assert "list_worker_tasks" in result
        assert "create_thrum" in result
        assert "list_thrums" in result
        assert "get_thrum" in result
        assert "update_thrum" in result
        assert "send_message" in result

    def test_with_workers(self):
        workers = {"oppy": {"description": "The architect"}}
        result = generate_conductor_identity(
            "kamaji", "The Clade", workers=workers
        )
        assert "## Workers" in result
        assert "**oppy**" in result
        assert "The architect" in result

    def test_with_brothers(self):
        brothers = {
            "doot": {"role": "coordinator", "description": "Personal assistant"},
        }
        result = generate_conductor_identity(
            "kamaji", "The Clade", brothers=brothers
        )
        assert "## Brothers" in result
        assert "**doot**" in result

    def test_no_personal_tools(self):
        result = generate_conductor_identity("kamaji", "The Clade")
        assert "spawn_terminal" not in result
        assert "connect_to_brother" not in result
        assert "initiate_ssh_task" not in result


class TestGenerateWorkerIdentity:
    def test_basic(self):
        result = generate_worker_identity("oppy", "The Clade")
        assert MARKER_START in result
        assert MARKER_END in result
        assert "**Name:** oppy" in result
        assert "**Role:** worker" in result
        assert "clade-worker" in result

    def test_with_personality(self):
        result = generate_worker_identity(
            "oppy", "The Clade", personality="Intellectual and curious"
        )
        assert "Intellectual and curious" in result

    def test_with_family(self):
        brothers = {
            "oppy": {"role": "worker", "description": "The architect"},
            "jerry": {"role": "worker", "description": "The runner"},
        }
        result = generate_worker_identity(
            "oppy", "The Clade",
            personal_name="doot",
            brothers=brothers,
        )
        assert "## Family" in result
        assert "**doot** (coordinator)" in result
        # Should not list self
        assert result.count("**oppy**") == 0
        assert "**jerry**" in result

    def test_worker_tools_only(self):
        result = generate_worker_identity("oppy", "The Clade")
        assert "send_message" in result
        assert "check_mailbox" in result
        # Should NOT have personal-only tools
        assert "spawn_terminal" not in result
        assert "initiate_ssh_task" not in result


class TestUpsertIdentitySection:
    def test_empty_content(self):
        identity = f"{MARKER_START}\nIdentity\n{MARKER_END}"
        result = upsert_identity_section("", identity)
        assert result == identity + "\n"

    def test_no_markers_appends(self):
        existing = "# My CLAUDE.md\n\nSome content here."
        identity = f"{MARKER_START}\nIdentity\n{MARKER_END}"
        result = upsert_identity_section(existing, identity)
        assert result.startswith("# My CLAUDE.md")
        assert result.endswith(identity + "\n")
        # Double newline separator
        assert "\n\n" + identity in result

    def test_markers_replace(self):
        existing = (
            "# Header\n\n"
            f"{MARKER_START}\nOld identity\n{MARKER_END}\n\n"
            "# Footer"
        )
        new_identity = f"{MARKER_START}\nNew identity\n{MARKER_END}"
        result = upsert_identity_section(existing, new_identity)
        assert "Old identity" not in result
        assert "New identity" in result
        assert "# Header" in result
        assert "# Footer" in result

    def test_idempotent(self):
        identity = f"{MARKER_START}\nIdentity\n{MARKER_END}"
        first = upsert_identity_section("", identity)
        second = upsert_identity_section(first, identity)
        assert first == second

    def test_only_start_marker_appends(self):
        """If only start marker found (no end), treat as no markers — append."""
        existing = f"# Header\n{MARKER_START}\nBroken content"
        identity = f"{MARKER_START}\nNew identity\n{MARKER_END}"
        result = upsert_identity_section(existing, identity)
        # Should append, not replace
        assert "Broken content" in result
        assert "New identity" in result

    def test_preserves_trailing_content_after_markers(self):
        existing = (
            f"{MARKER_START}\nOld\n{MARKER_END}\n\n"
            "# User content after identity"
        )
        identity = f"{MARKER_START}\nNew\n{MARKER_END}"
        result = upsert_identity_section(existing, identity)
        assert "# User content after identity" in result
        assert "Old" not in result


class TestWriteIdentityLocal:
    def test_new_file(self, tmp_path: Path):
        claude_md = tmp_path / ".claude" / "CLAUDE.md"
        identity = f"{MARKER_START}\nTest identity\n{MARKER_END}"

        result_path = write_identity_local(identity, claude_md)

        assert result_path == claude_md
        assert claude_md.exists()
        content = claude_md.read_text()
        assert "Test identity" in content
        assert MARKER_START in content
        assert MARKER_END in content

    def test_append_to_existing(self, tmp_path: Path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Existing content\n")
        identity = f"{MARKER_START}\nNew identity\n{MARKER_END}"

        write_identity_local(identity, claude_md)

        content = claude_md.read_text()
        assert "# Existing content" in content
        assert "New identity" in content

    def test_replace_existing_section(self, tmp_path: Path):
        claude_md = tmp_path / "CLAUDE.md"
        old = f"# Header\n\n{MARKER_START}\nOld\n{MARKER_END}\n\n# Footer\n"
        claude_md.write_text(old)
        identity = f"{MARKER_START}\nUpdated\n{MARKER_END}"

        write_identity_local(identity, claude_md)

        content = claude_md.read_text()
        assert "Old" not in content
        assert "Updated" in content
        assert "# Header" in content
        assert "# Footer" in content


class TestWriteIdentityRemote:
    @patch("clade.cli.identity.run_remote")
    def test_calls_run_remote(self, mock_run):
        mock_run.return_value = SSHResult(success=True, stdout="IDENTITY_OK")
        identity = f"{MARKER_START}\nTest\n{MARKER_END}"

        result = write_identity_remote("ian@masuda", identity)

        assert result.success
        assert "IDENTITY_OK" in result.stdout
        mock_run.assert_called_once()

        # Verify the script contains base64 + markers
        call_args = mock_run.call_args
        script = call_args[0][1]
        assert "base64" in script
        assert "CLADE_IDENTITY_START" in script
        assert "IDENTITY_OK" in script

    @patch("clade.cli.identity.run_remote")
    def test_ssh_failure(self, mock_run):
        mock_run.return_value = SSHResult(success=False, message="Connection refused")

        result = write_identity_remote("bad@host", "identity content")

        assert not result.success
