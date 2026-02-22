"""Tests for CladeConfig data model and YAML persistence."""

from pathlib import Path

import yaml

from clade.cli.clade_config import (
    BrotherEntry,
    CladeConfig,
    default_config_path,
    load_clade_config,
    save_clade_config,
)


class TestCladeConfig:
    def test_defaults(self):
        cfg = CladeConfig()
        assert cfg.clade_name == "My Clade"
        assert cfg.personal_name == "doot"
        assert cfg.server_url is None
        assert cfg.brothers == {}
        assert cfg.created  # auto-filled

    def test_custom_values(self):
        cfg = CladeConfig(
            clade_name="Test Clade",
            personal_name="testy",
            server_url="https://example.com",
        )
        assert cfg.clade_name == "Test Clade"
        assert cfg.personal_name == "testy"
        assert cfg.server_url == "https://example.com"


class TestBrotherEntry:
    def test_defaults(self):
        bro = BrotherEntry(ssh="ian@masuda")
        assert bro.ssh == "ian@masuda"
        assert bro.working_dir is None
        assert bro.role == "worker"
        assert bro.description == ""
        assert bro.personality == ""

    def test_custom(self):
        bro = BrotherEntry(
            ssh="ian@masuda",
            working_dir="~/projects/foo",
            role="worker",
            description="The architect",
            personality="Intellectual and curious",
        )
        assert bro.working_dir == "~/projects/foo"
        assert bro.description == "The architect"
        assert bro.personality == "Intellectual and curious"


class TestSaveAndLoad:
    def test_round_trip(self, tmp_path: Path):
        config_file = tmp_path / "clade.yaml"
        cfg = CladeConfig(
            clade_name="Round Trip Test",
            created="2026-02-13",
            personal_name="doot",
            personal_description="Test coordinator",
            personal_personality="Methodical and detail-oriented",
            server_url="https://example.com",
            server_ssh="ubuntu@example.com",
            server_ssh_key="~/.ssh/test.pem",
            brothers={
                "oppy": BrotherEntry(
                    ssh="ian@masuda",
                    working_dir="~/projects/OMTRA_oppy",
                    role="worker",
                    description="The architect",
                    personality="Intellectual and curious",
                ),
            },
        )
        save_clade_config(cfg, config_file)
        loaded = load_clade_config(config_file)

        assert loaded is not None
        assert loaded.clade_name == "Round Trip Test"
        assert loaded.created == "2026-02-13"
        assert loaded.personal_name == "doot"
        assert loaded.personal_description == "Test coordinator"
        assert loaded.personal_personality == "Methodical and detail-oriented"
        assert loaded.server_url == "https://example.com"
        assert loaded.server_ssh == "ubuntu@example.com"
        assert loaded.server_ssh_key == "~/.ssh/test.pem"
        assert "oppy" in loaded.brothers
        assert loaded.brothers["oppy"].ssh == "ian@masuda"
        assert loaded.brothers["oppy"].working_dir == "~/projects/OMTRA_oppy"
        assert loaded.brothers["oppy"].role == "worker"
        assert loaded.brothers["oppy"].description == "The architect"
        assert loaded.brothers["oppy"].personality == "Intellectual and curious"

    def test_save_without_server(self, tmp_path: Path):
        config_file = tmp_path / "clade.yaml"
        cfg = CladeConfig(clade_name="No Server")
        save_clade_config(cfg, config_file)

        with open(config_file) as f:
            data = yaml.safe_load(f)
        assert "server" not in data

    def test_save_without_brothers(self, tmp_path: Path):
        config_file = tmp_path / "clade.yaml"
        cfg = CladeConfig(clade_name="No Brothers")
        save_clade_config(cfg, config_file)

        with open(config_file) as f:
            data = yaml.safe_load(f)
        assert "brothers" not in data

    def test_load_nonexistent(self, tmp_path: Path):
        result = load_clade_config(tmp_path / "missing.yaml")
        assert result is None

    def test_load_empty_file(self, tmp_path: Path):
        config_file = tmp_path / "empty.yaml"
        config_file.write_text("")
        result = load_clade_config(config_file)
        assert result is None

    def test_load_invalid_yaml(self, tmp_path: Path):
        config_file = tmp_path / "bad.yaml"
        config_file.write_text("not: a: valid: [yaml")
        result = load_clade_config(config_file)
        assert result is None

    def test_creates_parent_dirs(self, tmp_path: Path):
        config_file = tmp_path / "deep" / "nested" / "clade.yaml"
        cfg = CladeConfig()
        save_clade_config(cfg, config_file)
        assert config_file.exists()


    def test_load_without_personality_fields(self, tmp_path: Path):
        """Configs written before personality was added should load with defaults."""
        config_file = tmp_path / "clade.yaml"
        data = {
            "clade": {"name": "Old Clade", "created": "2026-02-01"},
            "personal": {"name": "doot", "description": "Coordinator"},
            "brothers": {
                "oppy": {"ssh": "ian@masuda", "role": "worker", "description": "Architect"},
            },
        }
        with open(config_file, "w") as f:
            yaml.dump(data, f)

        loaded = load_clade_config(config_file)
        assert loaded is not None
        assert loaded.personal_personality == ""
        assert loaded.brothers["oppy"].personality == ""

    def test_personality_not_saved_when_empty(self, tmp_path: Path):
        """Empty personality should not appear in YAML output."""
        config_file = tmp_path / "clade.yaml"
        cfg = CladeConfig(
            clade_name="Test",
            personal_personality="",
            brothers={
                "oppy": BrotherEntry(ssh="ian@masuda", personality=""),
            },
        )
        save_clade_config(cfg, config_file)

        with open(config_file) as f:
            data = yaml.safe_load(f)
        assert "personality" not in data["personal"]
        assert "personality" not in data["brothers"]["oppy"]


class TestEmberFields:
    def test_defaults_none(self):
        bro = BrotherEntry(ssh="ian@masuda")
        assert bro.ember_port is None
        assert bro.ember_host is None

    def test_custom(self):
        bro = BrotherEntry(
            ssh="ian@masuda",
            ember_port=8100,
            ember_host="100.71.57.52",
        )
        assert bro.ember_port == 8100
        assert bro.ember_host == "100.71.57.52"

    def test_round_trip(self, tmp_path: Path):
        config_file = tmp_path / "clade.yaml"
        cfg = CladeConfig(
            brothers={
                "oppy": BrotherEntry(
                    ssh="ian@masuda",
                    ember_port=8100,
                    ember_host="100.71.57.52",
                ),
            },
        )
        save_clade_config(cfg, config_file)
        loaded = load_clade_config(config_file)

        assert loaded is not None
        assert loaded.brothers["oppy"].ember_port == 8100
        assert loaded.brothers["oppy"].ember_host == "100.71.57.52"

    def test_not_saved_when_none(self, tmp_path: Path):
        config_file = tmp_path / "clade.yaml"
        cfg = CladeConfig(
            brothers={
                "oppy": BrotherEntry(ssh="ian@masuda"),
            },
        )
        save_clade_config(cfg, config_file)

        with open(config_file) as f:
            data = yaml.safe_load(f)
        assert "ember_port" not in data["brothers"]["oppy"]
        assert "ember_host" not in data["brothers"]["oppy"]

    def test_load_without_ember_fields(self, tmp_path: Path):
        """Configs written before ember was added should load with None defaults."""
        config_file = tmp_path / "clade.yaml"
        data = {
            "clade": {"name": "Old Clade", "created": "2026-02-01"},
            "personal": {"name": "doot", "description": "Coordinator"},
            "brothers": {
                "oppy": {"ssh": "ian@masuda", "role": "worker"},
            },
        }
        with open(config_file, "w") as f:
            yaml.dump(data, f)

        loaded = load_clade_config(config_file)
        assert loaded is not None
        assert loaded.brothers["oppy"].ember_port is None
        assert loaded.brothers["oppy"].ember_host is None


class TestVerifySsl:
    def test_default_true(self):
        cfg = CladeConfig()
        assert cfg.verify_ssl is True

    def test_round_trip_false(self, tmp_path: Path):
        config_file = tmp_path / "clade.yaml"
        cfg = CladeConfig(
            server_url="https://example.com",
            verify_ssl=False,
        )
        save_clade_config(cfg, config_file)
        loaded = load_clade_config(config_file)

        assert loaded is not None
        assert loaded.verify_ssl is False

    def test_round_trip_true_not_saved(self, tmp_path: Path):
        """verify_ssl=True (default) should not appear in YAML output."""
        config_file = tmp_path / "clade.yaml"
        cfg = CladeConfig(server_url="https://example.com", verify_ssl=True)
        save_clade_config(cfg, config_file)

        with open(config_file) as f:
            data = yaml.safe_load(f)
        assert "verify_ssl" not in data.get("server", {})

    def test_false_saved_in_yaml(self, tmp_path: Path):
        """verify_ssl=False should be explicitly saved."""
        config_file = tmp_path / "clade.yaml"
        cfg = CladeConfig(server_url="https://example.com", verify_ssl=False)
        save_clade_config(cfg, config_file)

        with open(config_file) as f:
            data = yaml.safe_load(f)
        assert data["server"]["verify_ssl"] is False

    def test_load_without_verify_ssl(self, tmp_path: Path):
        """Configs written before verify_ssl was added should default to True."""
        config_file = tmp_path / "clade.yaml"
        data = {
            "clade": {"name": "Old Clade", "created": "2026-02-01"},
            "personal": {"name": "doot", "description": "Coordinator"},
            "server": {"url": "https://example.com"},
        }
        with open(config_file, "w") as f:
            yaml.dump(data, f)

        loaded = load_clade_config(config_file)
        assert loaded is not None
        assert loaded.verify_ssl is True

    def test_verify_ssl_false_creates_server_section(self, tmp_path: Path):
        """verify_ssl=False alone should create the server section."""
        config_file = tmp_path / "clade.yaml"
        cfg = CladeConfig(verify_ssl=False)
        save_clade_config(cfg, config_file)

        with open(config_file) as f:
            data = yaml.safe_load(f)
        assert "server" in data
        assert data["server"]["verify_ssl"] is False


class TestDefaultConfigPath:
    def test_returns_path(self):
        p = default_config_path()
        assert isinstance(p, Path)
        assert p.name == "clade.yaml"
        assert "clade" in str(p)

    def test_with_config_dir(self, tmp_path: Path):
        p = default_config_path(config_dir=tmp_path)
        assert p == tmp_path / "clade.yaml"
