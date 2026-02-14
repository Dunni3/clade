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

    def test_custom(self):
        bro = BrotherEntry(
            ssh="ian@masuda",
            working_dir="~/projects/foo",
            role="worker",
            description="The architect",
        )
        assert bro.working_dir == "~/projects/foo"
        assert bro.description == "The architect"


class TestSaveAndLoad:
    def test_round_trip(self, tmp_path: Path):
        config_file = tmp_path / "clade.yaml"
        cfg = CladeConfig(
            clade_name="Round Trip Test",
            created="2026-02-13",
            personal_name="doot",
            personal_description="Test coordinator",
            server_url="https://example.com",
            server_ssh="ubuntu@example.com",
            server_ssh_key="~/.ssh/test.pem",
            brothers={
                "oppy": BrotherEntry(
                    ssh="ian@masuda",
                    working_dir="~/projects/OMTRA_oppy",
                    role="worker",
                    description="The architect",
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
        assert loaded.server_url == "https://example.com"
        assert loaded.server_ssh == "ubuntu@example.com"
        assert loaded.server_ssh_key == "~/.ssh/test.pem"
        assert "oppy" in loaded.brothers
        assert loaded.brothers["oppy"].ssh == "ian@masuda"
        assert loaded.brothers["oppy"].working_dir == "~/projects/OMTRA_oppy"
        assert loaded.brothers["oppy"].role == "worker"
        assert loaded.brothers["oppy"].description == "The architect"

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


class TestDefaultConfigPath:
    def test_returns_path(self):
        p = default_config_path()
        assert isinstance(p, Path)
        assert p.name == "clade.yaml"
        assert "clade" in str(p)
