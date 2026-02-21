"""Tests for the kanban board system: database, API, client, and MCP tools."""

import os
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

os.environ.setdefault("MAILBOX_API_KEYS", "test-key-doot:doot,test-key-oppy:oppy,test-key-jerry:jerry,test-key-kamaji:kamaji,test-key-ian:ian")

from httpx import ASGITransport, AsyncClient

from hearth.app import app
from hearth import db as hearth_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DOOT_HEADERS = {"Authorization": "Bearer test-key-doot"}
OPPY_HEADERS = {"Authorization": "Bearer test-key-oppy"}
JERRY_HEADERS = {"Authorization": "Bearer test-key-jerry"}


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


# ---------------------------------------------------------------------------
# Database layer
# ---------------------------------------------------------------------------


class TestDatabaseCards:
    @pytest.mark.asyncio
    async def test_insert_and_get(self):
        card_id = await hearth_db.insert_card(
            creator="doot", title="Fix login bug"
        )
        assert card_id > 0

        card = await hearth_db.get_card(card_id)
        assert card is not None
        assert card["title"] == "Fix login bug"
        assert card["creator"] == "doot"
        assert card["col"] == "backlog"
        assert card["priority"] == "normal"
        assert card["assignee"] is None
        assert card["labels"] == []

    @pytest.mark.asyncio
    async def test_insert_with_labels(self):
        card_id = await hearth_db.insert_card(
            creator="doot",
            title="Add auth",
            labels=["feature", "security"],
        )
        card = await hearth_db.get_card(card_id)
        assert set(card["labels"]) == {"feature", "security"}

    @pytest.mark.asyncio
    async def test_get_card_not_found(self):
        card = await hearth_db.get_card(999)
        assert card is None

    @pytest.mark.asyncio
    async def test_list_excludes_archived_by_default(self):
        await hearth_db.insert_card(creator="doot", title="Active", col="todo")
        await hearth_db.insert_card(creator="doot", title="Archived", col="archived")

        cards = await hearth_db.get_cards()
        assert len(cards) == 1
        assert cards[0]["title"] == "Active"

    @pytest.mark.asyncio
    async def test_list_include_archived(self):
        await hearth_db.insert_card(creator="doot", title="Active", col="todo")
        await hearth_db.insert_card(creator="doot", title="Archived", col="archived")

        cards = await hearth_db.get_cards(include_archived=True)
        assert len(cards) == 2

    @pytest.mark.asyncio
    async def test_list_filter_col(self):
        await hearth_db.insert_card(creator="doot", title="Backlog", col="backlog")
        await hearth_db.insert_card(creator="doot", title="Todo", col="todo")

        cards = await hearth_db.get_cards(col="todo")
        assert len(cards) == 1
        assert cards[0]["title"] == "Todo"

    @pytest.mark.asyncio
    async def test_list_filter_assignee(self):
        await hearth_db.insert_card(creator="doot", title="Oppy's", assignee="oppy")
        await hearth_db.insert_card(creator="doot", title="Unassigned")

        cards = await hearth_db.get_cards(assignee="oppy")
        assert len(cards) == 1
        assert cards[0]["title"] == "Oppy's"

    @pytest.mark.asyncio
    async def test_list_filter_label(self):
        await hearth_db.insert_card(creator="doot", title="Labeled", labels=["bug"])
        await hearth_db.insert_card(creator="doot", title="No label")

        cards = await hearth_db.get_cards(label="bug")
        assert len(cards) == 1
        assert cards[0]["title"] == "Labeled"

    @pytest.mark.asyncio
    async def test_priority_ordering(self):
        await hearth_db.insert_card(creator="doot", title="Low", priority="low")
        await hearth_db.insert_card(creator="doot", title="Urgent", priority="urgent")
        await hearth_db.insert_card(creator="doot", title="Normal", priority="normal")

        cards = await hearth_db.get_cards()
        assert cards[0]["title"] == "Urgent"
        assert cards[1]["title"] == "Normal"
        assert cards[2]["title"] == "Low"

    @pytest.mark.asyncio
    async def test_update_card(self):
        card_id = await hearth_db.insert_card(creator="doot", title="Original")
        updated = await hearth_db.update_card(card_id, title="Updated", col="in_progress")
        assert updated is not None
        assert updated["title"] == "Updated"
        assert updated["col"] == "in_progress"

    @pytest.mark.asyncio
    async def test_update_labels(self):
        card_id = await hearth_db.insert_card(
            creator="doot", title="Test", labels=["old"]
        )
        updated = await hearth_db.update_card(card_id, labels=["new1", "new2"])
        assert set(updated["labels"]) == {"new1", "new2"}

    @pytest.mark.asyncio
    async def test_update_assignee_to_none(self):
        card_id = await hearth_db.insert_card(
            creator="doot", title="Test", assignee="oppy"
        )
        updated = await hearth_db.update_card(card_id, assignee=None)
        assert updated["assignee"] is None

    @pytest.mark.asyncio
    async def test_update_nonexistent(self):
        result = await hearth_db.update_card(999, title="nope")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_card(self):
        card_id = await hearth_db.insert_card(
            creator="doot", title="Doomed", labels=["x"]
        )
        deleted = await hearth_db.delete_card(card_id)
        assert deleted is True
        assert await hearth_db.get_card(card_id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        deleted = await hearth_db.delete_card(999)
        assert deleted is False

    @pytest.mark.asyncio
    async def test_bulk_label_fetch(self):
        await hearth_db.insert_card(creator="doot", title="A", labels=["x", "y"])
        await hearth_db.insert_card(creator="doot", title="B", labels=["z"])
        await hearth_db.insert_card(creator="doot", title="C")

        cards = await hearth_db.get_cards()
        by_title = {c["title"]: c for c in cards}
        assert set(by_title["A"]["labels"]) == {"x", "y"}
        assert by_title["B"]["labels"] == ["z"]
        assert by_title["C"]["labels"] == []

    @pytest.mark.asyncio
    async def test_insert_with_links(self):
        card_id = await hearth_db.insert_card(
            creator="doot",
            title="Linked card",
            links=[
                {"object_type": "task", "object_id": "42"},
                {"object_type": "morsel", "object_id": "7"},
            ],
        )
        card = await hearth_db.get_card(card_id)
        assert len(card["links"]) == 2
        types = {l["object_type"] for l in card["links"]}
        assert types == {"task", "morsel"}

    @pytest.mark.asyncio
    async def test_update_links(self):
        card_id = await hearth_db.insert_card(
            creator="doot",
            title="Test",
            links=[{"object_type": "task", "object_id": "1"}],
        )
        updated = await hearth_db.update_card(
            card_id,
            links=[{"object_type": "card", "object_id": "5"}],
        )
        assert len(updated["links"]) == 1
        assert updated["links"][0]["object_type"] == "card"
        assert updated["links"][0]["object_id"] == "5"

    @pytest.mark.asyncio
    async def test_bulk_link_fetch(self):
        await hearth_db.insert_card(
            creator="doot", title="A",
            links=[{"object_type": "task", "object_id": "1"}],
        )
        await hearth_db.insert_card(creator="doot", title="B")

        cards = await hearth_db.get_cards()
        by_title = {c["title"]: c for c in cards}
        assert len(by_title["A"]["links"]) == 1
        assert by_title["B"]["links"] == []

    @pytest.mark.asyncio
    async def test_delete_card_with_links(self):
        card_id = await hearth_db.insert_card(
            creator="doot", title="Doomed",
            links=[{"object_type": "task", "object_id": "1"}],
        )
        deleted = await hearth_db.delete_card(card_id)
        assert deleted is True
        assert await hearth_db.get_card(card_id) is None

    @pytest.mark.asyncio
    async def test_pagination(self):
        for i in range(5):
            await hearth_db.insert_card(creator="doot", title=f"Card {i}")

        page1 = await hearth_db.get_cards(limit=2, offset=0)
        assert len(page1) == 2

        page2 = await hearth_db.get_cards(limit=2, offset=2)
        assert len(page2) == 2

        page3 = await hearth_db.get_cards(limit=2, offset=4)
        assert len(page3) == 1


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


class TestAPICards:
    @pytest.mark.asyncio
    async def test_create_card(self, client):
        resp = await client.post(
            "/api/v1/kanban/cards",
            json={"title": "New feature"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "New feature"
        assert data["creator"] == "doot"
        assert data["col"] == "backlog"
        assert data["priority"] == "normal"
        assert data["labels"] == []

    @pytest.mark.asyncio
    async def test_create_card_full(self, client):
        resp = await client.post(
            "/api/v1/kanban/cards",
            json={
                "title": "Urgent fix",
                "description": "Fix ASAP",
                "col": "todo",
                "priority": "urgent",
                "assignee": "oppy",
                "labels": ["bug", "critical"],
            },
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "Urgent fix"
        assert data["col"] == "todo"
        assert data["priority"] == "urgent"
        assert data["assignee"] == "oppy"
        assert set(data["labels"]) == {"bug", "critical"}

    @pytest.mark.asyncio
    async def test_create_card_invalid_col(self, client):
        resp = await client.post(
            "/api/v1/kanban/cards",
            json={"title": "Bad col", "col": "invalid"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_card_invalid_priority(self, client):
        resp = await client.post(
            "/api/v1/kanban/cards",
            json={"title": "Bad priority", "priority": "mega"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_cards(self, client):
        await client.post("/api/v1/kanban/cards", json={"title": "A"}, headers=DOOT_HEADERS)
        await client.post("/api/v1/kanban/cards", json={"title": "B"}, headers=OPPY_HEADERS)

        resp = await client.get("/api/v1/kanban/cards", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_list_cards_filter(self, client):
        await client.post(
            "/api/v1/kanban/cards",
            json={"title": "Todo", "col": "todo"},
            headers=DOOT_HEADERS,
        )
        await client.post(
            "/api/v1/kanban/cards",
            json={"title": "Backlog"},
            headers=DOOT_HEADERS,
        )

        resp = await client.get(
            "/api/v1/kanban/cards",
            params={"col": "todo"},
            headers=DOOT_HEADERS,
        )
        cards = resp.json()
        assert len(cards) == 1
        assert cards[0]["title"] == "Todo"

    @pytest.mark.asyncio
    async def test_get_card(self, client):
        create_resp = await client.post(
            "/api/v1/kanban/cards",
            json={"title": "Detail test"},
            headers=DOOT_HEADERS,
        )
        card_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/kanban/cards/{card_id}", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["title"] == "Detail test"

    @pytest.mark.asyncio
    async def test_get_card_not_found(self, client):
        resp = await client.get("/api/v1/kanban/cards/999", headers=DOOT_HEADERS)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_card(self, client):
        create_resp = await client.post(
            "/api/v1/kanban/cards",
            json={"title": "Original"},
            headers=DOOT_HEADERS,
        )
        card_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/kanban/cards/{card_id}",
            json={"title": "Updated", "col": "in_progress"},
            headers=OPPY_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["title"] == "Updated"
        assert resp.json()["col"] == "in_progress"

    @pytest.mark.asyncio
    async def test_update_card_invalid_col(self, client):
        create_resp = await client.post(
            "/api/v1/kanban/cards",
            json={"title": "Test"},
            headers=DOOT_HEADERS,
        )
        card_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/kanban/cards/{card_id}",
            json={"col": "invalid"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_delete_card_creator(self, client):
        create_resp = await client.post(
            "/api/v1/kanban/cards",
            json={"title": "Doomed"},
            headers=DOOT_HEADERS,
        )
        card_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/kanban/cards/{card_id}", headers=DOOT_HEADERS)
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_card_admin(self, client):
        create_resp = await client.post(
            "/api/v1/kanban/cards",
            json={"title": "Doomed"},
            headers=OPPY_HEADERS,
        )
        card_id = create_resp.json()["id"]

        # doot is admin, can delete oppy's card
        resp = await client.delete(f"/api/v1/kanban/cards/{card_id}", headers=DOOT_HEADERS)
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_delete_card_forbidden(self, client):
        create_resp = await client.post(
            "/api/v1/kanban/cards",
            json={"title": "Protected"},
            headers=DOOT_HEADERS,
        )
        card_id = create_resp.json()["id"]

        # oppy is not creator and not admin
        resp = await client.delete(f"/api/v1/kanban/cards/{card_id}", headers=OPPY_HEADERS)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_card_with_links(self, client):
        resp = await client.post(
            "/api/v1/kanban/cards",
            json={
                "title": "Linked",
                "links": [
                    {"object_type": "task", "object_id": "42"},
                    {"object_type": "morsel", "object_id": "7"},
                ],
            },
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["links"]) == 2

    @pytest.mark.asyncio
    async def test_update_card_links(self, client):
        create_resp = await client.post(
            "/api/v1/kanban/cards",
            json={"title": "Test"},
            headers=DOOT_HEADERS,
        )
        card_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/kanban/cards/{card_id}",
            json={"links": [{"object_type": "tree", "object_id": "3"}]},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        assert len(resp.json()["links"]) == 1
        assert resp.json()["links"][0]["object_type"] == "tree"

    @pytest.mark.asyncio
    async def test_no_auth(self, client):
        resp = await client.post(
            "/api/v1/kanban/cards",
            json={"title": "No auth"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# MailboxClient
# ---------------------------------------------------------------------------


class TestMailboxClientCards:
    @pytest.mark.asyncio
    async def test_create_card(self):
        from clade.communication.mailbox_client import MailboxClient

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 1, "title": "Test", "col": "backlog"}
        mock_resp.raise_for_status = MagicMock()

        mc = MailboxClient("http://test", "key")

        import httpx
        from unittest.mock import AsyncMock, patch

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(httpx, "AsyncClient", return_value=mock_client):
            result = await mc.create_card(title="Test")
            assert result["id"] == 1
            mock_client.post.assert_called_once()
            call_kwargs = mock_client.post.call_args
            assert call_kwargs[1]["json"]["title"] == "Test"

    @pytest.mark.asyncio
    async def test_get_cards(self):
        from clade.communication.mailbox_client import MailboxClient

        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"id": 1}, {"id": 2}]
        mock_resp.raise_for_status = MagicMock()

        mc = MailboxClient("http://test", "key")

        import httpx
        from unittest.mock import AsyncMock, patch

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(httpx, "AsyncClient", return_value=mock_client):
            result = await mc.get_cards(col="todo", assignee="oppy")
            assert len(result) == 2
            call_kwargs = mock_client.get.call_args
            assert call_kwargs[1]["params"]["col"] == "todo"
            assert call_kwargs[1]["params"]["assignee"] == "oppy"

    @pytest.mark.asyncio
    async def test_delete_card(self):
        from clade.communication.mailbox_client import MailboxClient

        mock_resp = MagicMock()
        mock_resp.status_code = 204

        mc = MailboxClient("http://test", "key")

        import httpx
        from unittest.mock import AsyncMock, patch

        mock_client = AsyncMock()
        mock_client.delete.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch.object(httpx, "AsyncClient", return_value=mock_client):
            result = await mc.delete_card(1)
            assert result is True


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------


class TestKanbanMCPTools:
    @pytest.mark.asyncio
    async def test_not_configured(self):
        from mcp.server.fastmcp import FastMCP
        from clade.mcp.tools.kanban_tools import create_kanban_tools

        mcp = FastMCP("test")
        tools = create_kanban_tools(mcp, None)

        result = await tools["create_card"]("Test")
        assert "not configured" in result.lower()

        result = await tools["list_board"]()
        assert "not configured" in result.lower()

    @pytest.mark.asyncio
    async def test_create_card(self):
        from unittest.mock import AsyncMock
        from mcp.server.fastmcp import FastMCP
        from clade.mcp.tools.kanban_tools import create_kanban_tools

        mailbox = AsyncMock()
        mailbox.create_card.return_value = {"id": 1, "title": "Test", "col": "backlog"}

        mcp = FastMCP("test")
        tools = create_kanban_tools(mcp, mailbox)

        result = await tools["create_card"]("Test")
        assert "Card #1 created" in result
        mailbox.create_card.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_card_invalid_col(self):
        from unittest.mock import AsyncMock
        from mcp.server.fastmcp import FastMCP
        from clade.mcp.tools.kanban_tools import create_kanban_tools

        mailbox = AsyncMock()
        mcp = FastMCP("test")
        tools = create_kanban_tools(mcp, mailbox)

        result = await tools["create_card"]("Test", col="invalid")
        assert "Invalid column" in result
        mailbox.create_card.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_board(self):
        from unittest.mock import AsyncMock
        from mcp.server.fastmcp import FastMCP
        from clade.mcp.tools.kanban_tools import create_kanban_tools

        mailbox = AsyncMock()
        mailbox.get_cards.return_value = [
            {"id": 1, "title": "A", "col": "backlog", "priority": "normal", "assignee": None, "labels": []},
            {"id": 2, "title": "B", "col": "todo", "priority": "high", "assignee": "oppy", "labels": ["bug"]},
        ]

        mcp = FastMCP("test")
        tools = create_kanban_tools(mcp, mailbox)

        result = await tools["list_board"]()
        assert "BACKLOG" in result
        assert "TODO" in result
        assert "#1" in result
        assert "#2" in result

    @pytest.mark.asyncio
    async def test_move_card(self):
        from unittest.mock import AsyncMock
        from mcp.server.fastmcp import FastMCP
        from clade.mcp.tools.kanban_tools import create_kanban_tools

        mailbox = AsyncMock()
        mailbox.update_card.return_value = {"id": 1, "title": "Test", "col": "done"}

        mcp = FastMCP("test")
        tools = create_kanban_tools(mcp, mailbox)

        result = await tools["move_card"](1, "done")
        assert "moved to done" in result

    @pytest.mark.asyncio
    async def test_move_card_invalid_col(self):
        from unittest.mock import AsyncMock
        from mcp.server.fastmcp import FastMCP
        from clade.mcp.tools.kanban_tools import create_kanban_tools

        mailbox = AsyncMock()
        mcp = FastMCP("test")
        tools = create_kanban_tools(mcp, mailbox)

        result = await tools["move_card"](1, "invalid")
        assert "Invalid column" in result

    @pytest.mark.asyncio
    async def test_archive_card(self):
        from unittest.mock import AsyncMock
        from mcp.server.fastmcp import FastMCP
        from clade.mcp.tools.kanban_tools import create_kanban_tools

        mailbox = AsyncMock()
        mailbox.archive_card.return_value = {"id": 1, "title": "Test", "col": "archived"}

        mcp = FastMCP("test")
        tools = create_kanban_tools(mcp, mailbox)

        result = await tools["archive_card"](1)
        assert "archived" in result

    @pytest.mark.asyncio
    async def test_get_card(self):
        from unittest.mock import AsyncMock
        from mcp.server.fastmcp import FastMCP
        from clade.mcp.tools.kanban_tools import create_kanban_tools

        mailbox = AsyncMock()
        mailbox.get_card.return_value = {
            "id": 1,
            "title": "Test Card",
            "description": "Details here",
            "col": "in_progress",
            "priority": "high",
            "assignee": "oppy",
            "creator": "doot",
            "labels": ["feature"],
            "created_at": "2026-02-21T00:00:00Z",
            "updated_at": "2026-02-21T00:00:00Z",
        }

        mcp = FastMCP("test")
        tools = create_kanban_tools(mcp, mailbox)

        result = await tools["get_card"](1)
        assert "Test Card" in result
        assert "in_progress" in result
        assert "oppy" in result

    @pytest.mark.asyncio
    async def test_update_card(self):
        from unittest.mock import AsyncMock
        from mcp.server.fastmcp import FastMCP
        from clade.mcp.tools.kanban_tools import create_kanban_tools

        mailbox = AsyncMock()
        mailbox.update_card.return_value = {"id": 1, "title": "New Title", "col": "todo"}

        mcp = FastMCP("test")
        tools = create_kanban_tools(mcp, mailbox)

        result = await tools["update_card"](1, title="New Title")
        assert "updated" in result
