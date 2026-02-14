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


class TestDefaultConfigPath:
    def test_returns_path(self):
        p = default_config_path()
        assert isinstance(p, Path)
        assert p.name == "clade.yaml"
        assert "clade" in str(p)

    def test_with_config_dir(self, tmp_path: Path):
        p = default_config_path(config_dir=tmp_path)
        assert p == tmp_path / "clade.yaml"
