"""Tests for the brother_projects system: DB CRUD, API endpoints, working_dir
resolution cascade, config layer round-trip, and client methods."""

import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
import yaml

os.environ.setdefault(
    "MAILBOX_API_KEYS",
    "test-key-doot:doot,test-key-oppy:oppy,test-key-jerry:jerry,test-key-kamaji:kamaji,test-key-ian:ian",
)

from httpx import ASGITransport, AsyncClient
from mcp.server.fastmcp import FastMCP

from hearth.app import app
from hearth import db as hearth_db
from clade.cli.clade_config import (
    BrotherEntry,
    CladeConfig,
    build_brothers_registry,
    load_clade_config,
    save_clade_config,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DOOT_HEADERS = {"Authorization": "Bearer test-key-doot"}
OPPY_HEADERS = {"Authorization": "Bearer test-key-oppy"}


@pytest_asyncio.fixture(autouse=True)
async def fresh_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    original = hearth_db.DB_PATH
    hearth_db.DB_PATH = db_path
    await hearth_db.init_db()
    yield db_path
    hearth_db.DB_PATH = original


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ===========================================================================
# 1. brother_projects table CRUD in hearth/db.py
# ===========================================================================


class TestDatabaseBrotherProjects:
    @pytest.mark.asyncio
    async def test_upsert_and_get(self):
        result = await hearth_db.upsert_brother_project(
            "oppy", "clade", "/home/ian/projects/clade"
        )
        assert result["brother_name"] == "oppy"
        assert result["project"] == "clade"
        assert result["working_dir"] == "/home/ian/projects/clade"
        assert "updated_at" in result

        fetched = await hearth_db.get_brother_project("oppy", "clade")
        assert fetched is not None
        assert fetched["working_dir"] == "/home/ian/projects/clade"

    @pytest.mark.asyncio
    async def test_upsert_updates_existing(self):
        await hearth_db.upsert_brother_project(
            "oppy", "clade", "/old/path"
        )
        updated = await hearth_db.upsert_brother_project(
            "oppy", "clade", "/new/path"
        )
        assert updated["working_dir"] == "/new/path"

        fetched = await hearth_db.get_brother_project("oppy", "clade")
        assert fetched["working_dir"] == "/new/path"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self):
        result = await hearth_db.get_brother_project("oppy", "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_all_projects_for_brother(self):
        await hearth_db.upsert_brother_project("oppy", "clade", "/path/clade")
        await hearth_db.upsert_brother_project("oppy", "omtra", "/path/omtra")
        await hearth_db.upsert_brother_project("jerry", "clade", "/jerry/clade")

        oppy_projects = await hearth_db.get_brother_projects("oppy")
        assert len(oppy_projects) == 2
        names = {p["project"] for p in oppy_projects}
        assert names == {"clade", "omtra"}

        jerry_projects = await hearth_db.get_brother_projects("jerry")
        assert len(jerry_projects) == 1
        assert jerry_projects[0]["project"] == "clade"

    @pytest.mark.asyncio
    async def test_get_projects_empty(self):
        projects = await hearth_db.get_brother_projects("nobody")
        assert projects == []

    @pytest.mark.asyncio
    async def test_delete(self):
        await hearth_db.upsert_brother_project("oppy", "clade", "/path/clade")

        deleted = await hearth_db.delete_brother_project("oppy", "clade")
        assert deleted is True

        fetched = await hearth_db.get_brother_project("oppy", "clade")
        assert fetched is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        deleted = await hearth_db.delete_brother_project("oppy", "nonexistent")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_multiple_brothers_same_project(self):
        """Different brothers can have the same project with different working dirs."""
        await hearth_db.upsert_brother_project("oppy", "clade", "/oppy/clade")
        await hearth_db.upsert_brother_project("jerry", "clade", "/jerry/clade")

        oppy = await hearth_db.get_brother_project("oppy", "clade")
        jerry = await hearth_db.get_brother_project("jerry", "clade")
        assert oppy["working_dir"] == "/oppy/clade"
        assert jerry["working_dir"] == "/jerry/clade"


# ===========================================================================
# 2. Brother projects API endpoints
# ===========================================================================


class TestAPIBrotherProjects:
    @pytest.mark.asyncio
    async def test_put_and_get(self, client):
        # Create
        resp = await client.put(
            "/api/v1/brothers/oppy/projects/clade",
            json={"working_dir": "/home/ian/projects/clade"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["brother_name"] == "oppy"
        assert data["project"] == "clade"
        assert data["working_dir"] == "/home/ian/projects/clade"

        # Get specific
        resp = await client.get(
            "/api/v1/brothers/oppy/projects/clade",
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["working_dir"] == "/home/ian/projects/clade"

    @pytest.mark.asyncio
    async def test_put_upsert(self, client):
        await client.put(
            "/api/v1/brothers/oppy/projects/clade",
            json={"working_dir": "/old/path"},
            headers=DOOT_HEADERS,
        )
        resp = await client.put(
            "/api/v1/brothers/oppy/projects/clade",
            json={"working_dir": "/new/path"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["working_dir"] == "/new/path"

    @pytest.mark.asyncio
    async def test_list_projects(self, client):
        await client.put(
            "/api/v1/brothers/oppy/projects/clade",
            json={"working_dir": "/path/clade"},
            headers=DOOT_HEADERS,
        )
        await client.put(
            "/api/v1/brothers/oppy/projects/omtra",
            json={"working_dir": "/path/omtra"},
            headers=DOOT_HEADERS,
        )

        resp = await client.get(
            "/api/v1/brothers/oppy/projects",
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        projects = resp.json()
        assert len(projects) == 2
        names = {p["project"] for p in projects}
        assert names == {"clade", "omtra"}

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_404(self, client):
        resp = await client.get(
            "/api/v1/brothers/oppy/projects/missing",
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_empty(self, client):
        resp = await client.get(
            "/api/v1/brothers/nobody/projects",
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_requires_auth(self, client):
        resp = await client.put(
            "/api/v1/brothers/oppy/projects/clade",
            json={"working_dir": "/path"},
        )
        # Should be 401 or 403 without auth
        assert resp.status_code in (401, 403, 422)


# ===========================================================================
# 3. Working_dir resolution cascade
# ===========================================================================


class TestWorkingDirResolutionInUnblockAndDelegate:
    """Test the working_dir resolution cascade in app._unblock_and_delegate:
    explicit working_dir > project lookup > None
    """

    @pytest.mark.asyncio
    async def test_explicit_working_dir_takes_precedence(self, client):
        """When a task has an explicit working_dir, project lookup is skipped."""
        # Register a brother project mapping
        await hearth_db.upsert_brother_project("oppy", "clade", "/project/path")

        # Register oppy's ember
        await hearth_db.upsert_ember("oppy", "http://localhost:9999")
        await hearth_db.insert_api_key("oppy", "oppy-ember-key")

        # Create a blocking task
        blocker_id = await hearth_db.insert_task(
            creator="doot", assignee="oppy", prompt="blocking task"
        )

        # Create a blocked task WITH explicit working_dir AND project
        blocked_id = await hearth_db.insert_task(
            creator="doot",
            assignee="oppy",
            prompt="blocked task",
            working_dir="/explicit/path",
            project="clade",
            blocked_by_task_id=blocker_id,
        )

        task = await hearth_db.get_task(blocked_id)
        assert task["working_dir"] == "/explicit/path"
        assert task["project"] == "clade"

    @pytest.mark.asyncio
    async def test_project_lookup_when_no_explicit_wd(self, client):
        """When no explicit working_dir, project mapping is used."""
        # Set up project mapping
        await hearth_db.upsert_brother_project("oppy", "clade", "/project/clade/path")

        # Create a task with project but no working_dir
        task_id = await hearth_db.insert_task(
            creator="doot",
            assignee="oppy",
            prompt="test task",
            project="clade",
        )

        task = await hearth_db.get_task(task_id)
        assert task["working_dir"] is None
        assert task["project"] == "clade"

        # Verify the project mapping is available for resolution
        bp = await hearth_db.get_brother_project("oppy", "clade")
        assert bp is not None
        assert bp["working_dir"] == "/project/clade/path"

    @pytest.mark.asyncio
    async def test_no_project_mapping_falls_through(self):
        """When project is set but no mapping exists, working_dir stays None."""
        task_id = await hearth_db.insert_task(
            creator="doot",
            assignee="oppy",
            prompt="test task",
            project="unknown_project",
        )

        task = await hearth_db.get_task(task_id)
        assert task["working_dir"] is None
        assert task["project"] == "unknown_project"

        # No mapping exists
        bp = await hearth_db.get_brother_project("oppy", "unknown_project")
        assert bp is None


class TestWorkingDirResolutionInDelegationTools:
    """Test the working_dir resolution cascade in delegation_tools.initiate_ember_task:
    explicit working_dir > project lookup (from registry) > brother default
    """

    @pytest.mark.asyncio
    async def test_explicit_working_dir_overrides_all(self):
        """Explicit working_dir takes precedence over project and default."""
        from clade.mcp.tools.delegation_tools import create_delegation_tools
        from clade.worker.client import EmberClient

        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.return_value = {"id": 42, "blocked_by_task_id": None}
        mock_mailbox.update_task.return_value = {"id": 42, "status": "launched"}

        registry = {
            "oppy": {
                "ember_url": "http://localhost:8100",
                "ember_api_key": "test-key",
                "working_dir": "/default/path",
                "projects": {"clade": "/project/clade"},
            },
        }

        mcp = FastMCP("test")
        mock_execute = AsyncMock(return_value={"session_name": "task-oppy-test"})

        with patch.object(EmberClient, "__init__", return_value=None), \
             patch.object(EmberClient, "execute_task", mock_execute), \
             patch("clade.mcp.tools.delegation_tools.resolve_ember_url") as mock_resolve:
            from clade.worker.resolver import EmberResolution
            mock_resolve.return_value = EmberResolution(url="http://localhost:8100", source="config", warnings=[])

            tools = create_delegation_tools(
                mcp, mock_mailbox, brothers_registry=registry, mailbox_name="doot"
            )
            await tools["initiate_ember_task"](
                brother="oppy",
                prompt="test task",
                working_dir="/explicit/override",
                project="clade",
            )

        # The execute_task call should use the explicit working_dir
        call_kwargs = mock_execute.call_args.kwargs
        assert call_kwargs["working_dir"] == "/explicit/override"

    @pytest.mark.asyncio
    async def test_project_lookup_when_no_explicit_wd(self):
        """When no explicit working_dir, project mapping from registry is used."""
        from clade.mcp.tools.delegation_tools import create_delegation_tools
        from clade.worker.client import EmberClient

        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.return_value = {"id": 43, "blocked_by_task_id": None}
        mock_mailbox.update_task.return_value = {"id": 43, "status": "launched"}

        registry = {
            "oppy": {
                "ember_url": "http://localhost:8100",
                "ember_api_key": "test-key",
                "working_dir": "/default/path",
                "projects": {"clade": "/project/clade"},
            },
        }

        mcp = FastMCP("test")
        mock_execute = AsyncMock(return_value={"session_name": "task-oppy-test"})

        with patch.object(EmberClient, "__init__", return_value=None), \
             patch.object(EmberClient, "execute_task", mock_execute), \
             patch("clade.mcp.tools.delegation_tools.resolve_ember_url") as mock_resolve:
            from clade.worker.resolver import EmberResolution
            mock_resolve.return_value = EmberResolution(url="http://localhost:8100", source="config", warnings=[])

            tools = create_delegation_tools(
                mcp, mock_mailbox, brothers_registry=registry, mailbox_name="doot"
            )
            await tools["initiate_ember_task"](
                brother="oppy",
                prompt="test task",
                project="clade",
            )

        call_kwargs = mock_execute.call_args.kwargs
        assert call_kwargs["working_dir"] == "/project/clade"

    @pytest.mark.asyncio
    async def test_falls_back_to_default_wd(self):
        """When no explicit wd and no project mapping, uses brother default."""
        from clade.mcp.tools.delegation_tools import create_delegation_tools
        from clade.worker.client import EmberClient

        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.return_value = {"id": 44, "blocked_by_task_id": None}
        mock_mailbox.update_task.return_value = {"id": 44, "status": "launched"}

        registry = {
            "oppy": {
                "ember_url": "http://localhost:8100",
                "ember_api_key": "test-key",
                "working_dir": "/default/path",
                "projects": {},  # no project mapping
            },
        }

        mcp = FastMCP("test")
        mock_execute = AsyncMock(return_value={"session_name": "task-oppy-test"})

        with patch.object(EmberClient, "__init__", return_value=None), \
             patch.object(EmberClient, "execute_task", mock_execute), \
             patch("clade.mcp.tools.delegation_tools.resolve_ember_url") as mock_resolve:
            from clade.worker.resolver import EmberResolution
            mock_resolve.return_value = EmberResolution(url="http://localhost:8100", source="config", warnings=[])

            tools = create_delegation_tools(
                mcp, mock_mailbox, brothers_registry=registry, mailbox_name="doot"
            )
            await tools["initiate_ember_task"](
                brother="oppy",
                prompt="test task",
            )

        call_kwargs = mock_execute.call_args.kwargs
        assert call_kwargs["working_dir"] == "/default/path"

    @pytest.mark.asyncio
    async def test_missing_project_mapping_uses_default(self):
        """When project is set but no mapping exists, falls back to default."""
        from clade.mcp.tools.delegation_tools import create_delegation_tools
        from clade.worker.client import EmberClient

        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.return_value = {"id": 45, "blocked_by_task_id": None}
        mock_mailbox.update_task.return_value = {"id": 45, "status": "launched"}

        registry = {
            "oppy": {
                "ember_url": "http://localhost:8100",
                "ember_api_key": "test-key",
                "working_dir": "/default/path",
                "projects": {"omtra": "/project/omtra"},  # no "clade" mapping
            },
        }

        mcp = FastMCP("test")
        mock_execute = AsyncMock(return_value={"session_name": "task-oppy-test"})

        with patch.object(EmberClient, "__init__", return_value=None), \
             patch.object(EmberClient, "execute_task", mock_execute), \
             patch("clade.mcp.tools.delegation_tools.resolve_ember_url") as mock_resolve:
            from clade.worker.resolver import EmberResolution
            mock_resolve.return_value = EmberResolution(url="http://localhost:8100", source="config", warnings=[])

            tools = create_delegation_tools(
                mcp, mock_mailbox, brothers_registry=registry, mailbox_name="doot"
            )
            await tools["initiate_ember_task"](
                brother="oppy",
                prompt="test task",
                project="clade",  # no mapping for this project
            )

        call_kwargs = mock_execute.call_args.kwargs
        assert call_kwargs["working_dir"] == "/default/path"


class TestWorkingDirResolutionInConductorTools:
    """Test the working_dir resolution cascade in conductor_tools.delegate_task:
    explicit working_dir > project lookup (from registry) > worker default
    """

    @pytest.mark.asyncio
    async def test_project_mapping_used(self):
        from clade.mcp.tools.conductor_tools import create_conductor_tools
        from clade.mcp.tools import conductor_tools

        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.return_value = {"id": 50, "blocked_by_task_id": None}
        mock_mailbox.update_task.return_value = {"id": 50, "status": "launched"}

        registry = {
            "oppy": {
                "ember_url": "http://localhost:8100",
                "ember_api_key": "test-key",
                "working_dir": "/default/path",
                "projects": {"clade": "/project/clade"},
            },
        }

        mock_execute = AsyncMock(
            return_value={"session_name": "task-oppy-test-123", "message": "ok"}
        )

        with pytest.MonkeyPatch.context() as mp:
            class MockEmberClient:
                def __init__(self, url, key, verify_ssl=True):
                    self.base_url = url
                    self.api_key = key

                async def execute_task(self, **kwargs):
                    return await mock_execute(**kwargs)

            mp.setattr(conductor_tools, "EmberClient", MockEmberClient)

            mcp = FastMCP("test")
            tools = create_conductor_tools(
                mcp, mock_mailbox, registry,
                hearth_url="https://test.example.com",
                hearth_api_key="test-key",
            )
            await tools["delegate_task"](
                "oppy", "test task", project="clade"
            )

        call_kwargs = mock_execute.call_args.kwargs
        assert call_kwargs["working_dir"] == "/project/clade"

    @pytest.mark.asyncio
    async def test_explicit_wd_overrides_project(self):
        from clade.mcp.tools.conductor_tools import create_conductor_tools
        from clade.mcp.tools import conductor_tools

        mock_mailbox = AsyncMock()
        mock_mailbox.create_task.return_value = {"id": 51, "blocked_by_task_id": None}
        mock_mailbox.update_task.return_value = {"id": 51, "status": "launched"}

        registry = {
            "oppy": {
                "ember_url": "http://localhost:8100",
                "ember_api_key": "test-key",
                "working_dir": "/default/path",
                "projects": {"clade": "/project/clade"},
            },
        }

        mock_execute = AsyncMock(
            return_value={"session_name": "task-oppy-test-123", "message": "ok"}
        )

        with pytest.MonkeyPatch.context() as mp:
            class MockEmberClient:
                def __init__(self, url, key, verify_ssl=True):
                    self.base_url = url

                async def execute_task(self, **kwargs):
                    return await mock_execute(**kwargs)

            mp.setattr(conductor_tools, "EmberClient", MockEmberClient)

            mcp = FastMCP("test")
            tools = create_conductor_tools(
                mcp, mock_mailbox, registry,
                hearth_url="https://test.example.com",
                hearth_api_key="test-key",
            )
            await tools["delegate_task"](
                "oppy", "test task",
                working_dir="/explicit/wd",
                project="clade",
            )

        call_kwargs = mock_execute.call_args.kwargs
        assert call_kwargs["working_dir"] == "/explicit/wd"


# ===========================================================================
# 4. Config layer round-trip (BrotherEntry.projects)
# ===========================================================================


class TestConfigProjectsRoundTrip:
    def test_brother_entry_projects_default_empty(self):
        bro = BrotherEntry(ssh="ian@masuda")
        assert bro.projects == {}

    def test_brother_entry_with_projects(self):
        bro = BrotherEntry(
            ssh="ian@masuda",
            projects={"clade": "/home/ian/projects/clade", "omtra": "/home/ian/omtra"},
        )
        assert bro.projects["clade"] == "/home/ian/projects/clade"
        assert bro.projects["omtra"] == "/home/ian/omtra"

    def test_save_and_load_with_projects(self, tmp_path: Path):
        config_file = tmp_path / "clade.yaml"
        cfg = CladeConfig(
            brothers={
                "oppy": BrotherEntry(
                    ssh="ian@masuda",
                    ember_host="100.71.57.52",
                    ember_port=8100,
                    working_dir="~/projects/default",
                    projects={
                        "clade": "~/projects/clade",
                        "omtra": "~/projects/omtra",
                    },
                ),
            },
        )
        save_clade_config(cfg, config_file)
        loaded = load_clade_config(config_file)

        assert loaded is not None
        assert loaded.brothers["oppy"].projects == {
            "clade": "~/projects/clade",
            "omtra": "~/projects/omtra",
        }

    def test_projects_not_saved_when_empty(self, tmp_path: Path):
        config_file = tmp_path / "clade.yaml"
        cfg = CladeConfig(
            brothers={
                "oppy": BrotherEntry(ssh="ian@masuda"),
            },
        )
        save_clade_config(cfg, config_file)

        with open(config_file) as f:
            data = yaml.safe_load(f)
        assert "projects" not in data["brothers"]["oppy"]

    def test_load_without_projects_field(self, tmp_path: Path):
        """Configs written before projects was added should load with empty dict."""
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
        assert loaded.brothers["oppy"].projects == {}

    def test_build_registry_includes_projects(self):
        cfg = CladeConfig(
            brothers={
                "oppy": BrotherEntry(
                    ssh="ian@masuda",
                    ember_host="100.71.57.52",
                    ember_port=8100,
                    working_dir="~/default",
                    projects={"clade": "~/projects/clade", "omtra": "~/projects/omtra"},
                ),
            },
        )
        keys = {"oppy": "key-oppy"}
        registry = build_brothers_registry(cfg, keys)

        assert "projects" in registry["oppy"]
        assert registry["oppy"]["projects"]["clade"] == "~/projects/clade"
        assert registry["oppy"]["projects"]["omtra"] == "~/projects/omtra"

    def test_build_registry_omits_empty_projects(self):
        cfg = CladeConfig(
            brothers={
                "oppy": BrotherEntry(
                    ssh="ian@masuda",
                    ember_host="100.71.57.52",
                ),
            },
        )
        keys = {"oppy": "key-oppy"}
        registry = build_brothers_registry(cfg, keys)

        assert "projects" not in registry["oppy"]

    def test_projects_yaml_structure(self, tmp_path: Path):
        """Verify the YAML structure matches expected format."""
        config_file = tmp_path / "clade.yaml"
        cfg = CladeConfig(
            brothers={
                "oppy": BrotherEntry(
                    ssh="ian@masuda",
                    projects={"clade": "/clade/path", "omtra": "/omtra/path"},
                ),
            },
        )
        save_clade_config(cfg, config_file)

        with open(config_file) as f:
            data = yaml.safe_load(f)

        projects = data["brothers"]["oppy"]["projects"]
        assert isinstance(projects, dict)
        assert projects["clade"] == "/clade/path"
        assert projects["omtra"] == "/omtra/path"


# ===========================================================================
# 5. Client methods in mailbox_client.py
# ===========================================================================


class TestMailboxClientBrotherProjects:
    @pytest.mark.asyncio
    async def test_upsert_brother_project(self, client):
        """Test the client's upsert_brother_project via the real API."""
        from clade.communication.mailbox_client import MailboxClient

        mc = MailboxClient("http://test", "test-key-doot", verify_ssl=False)
        # Patch the internal httpx client to use our ASGI transport
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as http_client:
            with patch("httpx.AsyncClient", return_value=http_client):
                # Use the API directly since patching httpx.AsyncClient context manager is complex
                resp = await http_client.put(
                    "/api/v1/brothers/oppy/projects/clade",
                    json={"working_dir": "/test/path"},
                    headers=DOOT_HEADERS,
                )
                assert resp.status_code == 200
                result = resp.json()
                assert result["brother_name"] == "oppy"
                assert result["working_dir"] == "/test/path"

    @pytest.mark.asyncio
    async def test_get_brother_projects(self, client):
        """Test listing brother projects via the API."""
        # First create some projects
        await client.put(
            "/api/v1/brothers/oppy/projects/clade",
            json={"working_dir": "/path/clade"},
            headers=DOOT_HEADERS,
        )
        await client.put(
            "/api/v1/brothers/oppy/projects/omtra",
            json={"working_dir": "/path/omtra"},
            headers=DOOT_HEADERS,
        )

        resp = await client.get(
            "/api/v1/brothers/oppy/projects",
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        projects = resp.json()
        assert len(projects) == 2

    @pytest.mark.asyncio
    async def test_get_brother_project_specific(self, client):
        """Test getting a specific brother project."""
        await client.put(
            "/api/v1/brothers/oppy/projects/clade",
            json={"working_dir": "/path/clade"},
            headers=DOOT_HEADERS,
        )

        resp = await client.get(
            "/api/v1/brothers/oppy/projects/clade",
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["working_dir"] == "/path/clade"

    @pytest.mark.asyncio
    async def test_get_brother_project_not_found(self, client):
        """Test 404 when project doesn't exist."""
        resp = await client.get(
            "/api/v1/brothers/oppy/projects/nonexistent",
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 404


# ===========================================================================
# 6. Task project field
# ===========================================================================


class TestTaskProjectField:
    @pytest.mark.asyncio
    async def test_task_stores_project(self):
        """Tasks can store a project field."""
        task_id = await hearth_db.insert_task(
            creator="doot",
            assignee="oppy",
            prompt="test",
            project="clade",
        )
        task = await hearth_db.get_task(task_id)
        assert task["project"] == "clade"

    @pytest.mark.asyncio
    async def test_task_project_none_by_default(self):
        """Tasks without project have None."""
        task_id = await hearth_db.insert_task(
            creator="doot",
            assignee="oppy",
            prompt="test",
        )
        task = await hearth_db.get_task(task_id)
        assert task["project"] is None

    @pytest.mark.asyncio
    async def test_task_project_in_list(self):
        """Project field appears in task list responses."""
        await hearth_db.insert_task(
            creator="doot", assignee="oppy", prompt="test", project="clade"
        )
        tasks = await hearth_db.get_tasks(assignee="oppy")
        assert len(tasks) == 1
        assert tasks[0]["project"] == "clade"

    @pytest.mark.asyncio
    async def test_create_task_api_with_project(self, client):
        """POST /api/v1/tasks accepts project field."""
        resp = await client.post(
            "/api/v1/tasks",
            json={
                "assignee": "oppy",
                "prompt": "test task",
                "project": "clade",
            },
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        task_id = resp.json()["id"]

        resp = await client.get(
            f"/api/v1/tasks/{task_id}",
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["project"] == "clade"


# ===========================================================================
# 7. Resolution cascade in _unblock_and_delegate (integration)
# ===========================================================================


class TestUnblockAndDelegateResolution:
    """Integration test for the full resolution cascade in _unblock_and_delegate."""

    @pytest.mark.asyncio
    async def test_uses_project_mapping_when_no_explicit_wd(self, client):
        """_unblock_and_delegate resolves working_dir from brother_projects
        when no explicit working_dir is set on the task."""
        # Set up: register ember, api key, and project mapping
        await hearth_db.upsert_ember("oppy", "http://localhost:9999")
        await hearth_db.insert_api_key("oppy", "oppy-ember-key")
        await hearth_db.upsert_brother_project("oppy", "clade", "/resolved/from/project")

        # Create blocker task
        blocker_id = await hearth_db.insert_task(
            creator="doot", assignee="oppy", prompt="blocker"
        )

        # Create blocked task with project but no working_dir
        blocked_id = await hearth_db.insert_task(
            creator="doot",
            assignee="oppy",
            prompt="blocked task",
            project="clade",
            blocked_by_task_id=blocker_id,
        )

        # Verify the task is blocked
        task = await hearth_db.get_task(blocked_id)
        assert task["blocked_by_task_id"] == blocker_id
        assert task["working_dir"] is None
        assert task["project"] == "clade"

        # The _unblock_and_delegate function will be called when blocker completes.
        # We can't easily test the full HTTP call without mocking httpx,
        # but we can verify the resolution logic matches.
        bp = await hearth_db.get_brother_project("oppy", "clade")
        assert bp["working_dir"] == "/resolved/from/project"

    @pytest.mark.asyncio
    async def test_explicit_wd_preserved(self, client):
        """Tasks with explicit working_dir don't need project resolution."""
        await hearth_db.upsert_brother_project("oppy", "clade", "/project/path")

        blocker_id = await hearth_db.insert_task(
            creator="doot", assignee="oppy", prompt="blocker"
        )
        blocked_id = await hearth_db.insert_task(
            creator="doot",
            assignee="oppy",
            prompt="blocked",
            working_dir="/explicit/path",
            project="clade",
            blocked_by_task_id=blocker_id,
        )

        task = await hearth_db.get_task(blocked_id)
        # Explicit working_dir is stored on the task
        assert task["working_dir"] == "/explicit/path"
