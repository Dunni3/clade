"""Tests for automatic kanban card syncing with task status changes."""

import os

import pytest
import pytest_asyncio

os.environ.setdefault(
    "MAILBOX_API_KEYS",
    "test-key-doot:doot,test-key-oppy:oppy,test-key-jerry:jerry,test-key-kamaji:kamaji,test-key-ian:ian",
)

from httpx import ASGITransport, AsyncClient

from hearth.app import app
from hearth import db as hearth_db


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


async def _create_task(client, assignee="oppy", subject="test task"):
    resp = await client.post(
        "/api/v1/tasks",
        json={"assignee": assignee, "prompt": "do something", "subject": subject},
        headers=DOOT_HEADERS,
    )
    assert resp.status_code == 200
    return resp.json()["id"]


async def _create_card_with_task_links(client, task_ids, col="in_progress"):
    resp = await client.post(
        "/api/v1/kanban/cards",
        json={
            "title": "Test card",
            "col": col,
            "links": [{"object_type": "task", "object_id": str(tid)} for tid in task_ids],
        },
        headers=DOOT_HEADERS,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def _update_task_status(client, task_id, status, output=None):
    payload = {"status": status}
    if output:
        payload["output"] = output
    resp = await client.patch(
        f"/api/v1/tasks/{task_id}",
        json=payload,
        headers=OPPY_HEADERS,
    )
    return resp


async def _get_card(client, card_id):
    resp = await client.get(f"/api/v1/kanban/cards/{card_id}", headers=DOOT_HEADERS)
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# _sync_linked_cards_to_done tests
# ---------------------------------------------------------------------------


class TestSyncCardsToDone:
    """Test auto-moving cards to done when all linked tasks complete."""

    @pytest.mark.asyncio
    async def test_single_task_completed_moves_card_to_done(self, client):
        task_id = await _create_task(client)
        card_id = await _create_card_with_task_links(client, [task_id])

        # Move task to in_progress then completed
        await _update_task_status(client, task_id, "in_progress")
        await _update_task_status(client, task_id, "completed")

        card = await _get_card(client, card_id)
        assert card["col"] == "done"

    @pytest.mark.asyncio
    async def test_all_tasks_completed_moves_card_to_done(self, client):
        t1 = await _create_task(client, subject="task 1")
        t2 = await _create_task(client, subject="task 2")
        card_id = await _create_card_with_task_links(client, [t1, t2])

        # Complete first task — card should stay in_progress (t2 still pending)
        await _update_task_status(client, t1, "in_progress")
        await _update_task_status(client, t1, "completed")
        card = await _get_card(client, card_id)
        assert card["col"] == "in_progress"

        # Complete second task — now card should move to done
        await _update_task_status(client, t2, "in_progress")
        await _update_task_status(client, t2, "completed")
        card = await _get_card(client, card_id)
        assert card["col"] == "done"

    @pytest.mark.asyncio
    async def test_completed_plus_failed_moves_card_to_done(self, client):
        t1 = await _create_task(client, subject="task 1")
        t2 = await _create_task(client, subject="task 2")
        card_id = await _create_card_with_task_links(client, [t1, t2])

        # One completes, one fails — should still move to done
        await _update_task_status(client, t1, "in_progress")
        await _update_task_status(client, t1, "completed")
        await _update_task_status(client, t2, "in_progress")
        await _update_task_status(client, t2, "failed")

        card = await _get_card(client, card_id)
        assert card["col"] == "done"

    @pytest.mark.asyncio
    async def test_all_failed_does_not_move_card_to_done(self, client):
        t1 = await _create_task(client, subject="task 1")
        t2 = await _create_task(client, subject="task 2")
        card_id = await _create_card_with_task_links(client, [t1, t2])

        await _update_task_status(client, t1, "in_progress")
        await _update_task_status(client, t1, "failed")
        await _update_task_status(client, t2, "in_progress")
        await _update_task_status(client, t2, "failed")

        card = await _get_card(client, card_id)
        assert card["col"] == "in_progress"

    @pytest.mark.asyncio
    async def test_all_killed_does_not_move_card_to_done(self, client):
        t1 = await _create_task(client)
        card_id = await _create_card_with_task_links(client, [t1])

        await _update_task_status(client, t1, "in_progress")
        # Kill via the kill endpoint
        resp = await client.post(f"/api/v1/tasks/{t1}/kill", headers=DOOT_HEADERS)
        assert resp.status_code == 200

        card = await _get_card(client, card_id)
        assert card["col"] == "in_progress"

    @pytest.mark.asyncio
    async def test_completed_plus_killed_moves_card_to_done(self, client):
        t1 = await _create_task(client, subject="task 1")
        t2 = await _create_task(client, subject="task 2")
        card_id = await _create_card_with_task_links(client, [t1, t2])

        await _update_task_status(client, t1, "in_progress")
        await _update_task_status(client, t1, "completed")
        await _update_task_status(client, t2, "in_progress")
        resp = await client.post(f"/api/v1/tasks/{t2}/kill", headers=DOOT_HEADERS)
        assert resp.status_code == 200

        card = await _get_card(client, card_id)
        assert card["col"] == "done"

    @pytest.mark.asyncio
    async def test_active_task_blocks_done(self, client):
        t1 = await _create_task(client, subject="task 1")
        t2 = await _create_task(client, subject="task 2")
        card_id = await _create_card_with_task_links(client, [t1, t2])

        # t1 completes, t2 still in_progress
        await _update_task_status(client, t1, "in_progress")
        await _update_task_status(client, t1, "completed")
        await _update_task_status(client, t2, "in_progress")

        card = await _get_card(client, card_id)
        assert card["col"] == "in_progress"

    @pytest.mark.asyncio
    async def test_card_no_linked_tasks_untouched(self, client):
        """A card with no task links should not be affected."""
        resp = await client.post(
            "/api/v1/kanban/cards",
            json={"title": "No links", "col": "in_progress"},
            headers=DOOT_HEADERS,
        )
        card_id = resp.json()["id"]

        # Create and complete an unrelated task
        t1 = await _create_task(client)
        await _update_task_status(client, t1, "in_progress")
        await _update_task_status(client, t1, "completed")

        card = await _get_card(client, card_id)
        assert card["col"] == "in_progress"

    @pytest.mark.asyncio
    async def test_card_already_done_not_regressed(self, client):
        """A card already in 'done' should not be touched again."""
        t1 = await _create_task(client)
        card_id = await _create_card_with_task_links(client, [t1], col="done")

        await _update_task_status(client, t1, "in_progress")
        await _update_task_status(client, t1, "completed")

        card = await _get_card(client, card_id)
        assert card["col"] == "done"

    @pytest.mark.asyncio
    async def test_card_already_archived_not_regressed(self, client):
        t1 = await _create_task(client)
        card_id = await _create_card_with_task_links(client, [t1], col="archived")

        await _update_task_status(client, t1, "in_progress")
        await _update_task_status(client, t1, "completed")

        card = await _get_card(client, card_id)
        assert card["col"] == "archived"

    @pytest.mark.asyncio
    async def test_multiple_cards_linked_to_same_task(self, client):
        t1 = await _create_task(client)
        card1 = await _create_card_with_task_links(client, [t1])
        card2 = await _create_card_with_task_links(client, [t1])

        await _update_task_status(client, t1, "in_progress")
        await _update_task_status(client, t1, "completed")

        c1 = await _get_card(client, card1)
        c2 = await _get_card(client, card2)
        assert c1["col"] == "done"
        assert c2["col"] == "done"


# ---------------------------------------------------------------------------
# Bidirectional re-opening tests
# ---------------------------------------------------------------------------


class TestBidirectionalReopen:
    """Test re-opening done cards when a new linked task becomes active."""

    @pytest.mark.asyncio
    async def test_done_card_reopens_on_new_task_in_progress(self, client):
        t1 = await _create_task(client, subject="original")
        card_id = await _create_card_with_task_links(client, [t1])

        # Complete the task -> card goes to done
        await _update_task_status(client, t1, "in_progress")
        await _update_task_status(client, t1, "completed")
        card = await _get_card(client, card_id)
        assert card["col"] == "done"

        # Create a new task and link it to the card
        t2 = await _create_task(client, subject="followup")
        await client.patch(
            f"/api/v1/kanban/cards/{card_id}",
            json={
                "links": [
                    {"object_type": "task", "object_id": str(t1)},
                    {"object_type": "task", "object_id": str(t2)},
                ],
            },
            headers=DOOT_HEADERS,
        )

        # Move new task to in_progress -> card should reopen
        await _update_task_status(client, t2, "in_progress")
        card = await _get_card(client, card_id)
        assert card["col"] == "in_progress"

    @pytest.mark.asyncio
    async def test_archived_card_not_reopened(self, client):
        """Archived cards should never be re-opened."""
        t1 = await _create_task(client)
        card_id = await _create_card_with_task_links(client, [t1], col="archived")

        await _update_task_status(client, t1, "in_progress")

        card = await _get_card(client, card_id)
        assert card["col"] == "archived"


# ---------------------------------------------------------------------------
# DB helper tests
# ---------------------------------------------------------------------------


class TestGetLinkedTaskStatuses:
    @pytest.mark.asyncio
    async def test_returns_statuses(self):
        t1 = await hearth_db.insert_task(
            creator="doot", assignee="oppy", prompt="p", subject="s"
        )
        t2 = await hearth_db.insert_task(
            creator="doot", assignee="oppy", prompt="p", subject="s"
        )
        await hearth_db.update_task(t1, status="completed")
        await hearth_db.update_task(t2, status="failed")

        card_id = await hearth_db.insert_card(
            creator="doot",
            title="Test",
            links=[
                {"object_type": "task", "object_id": str(t1)},
                {"object_type": "task", "object_id": str(t2)},
            ],
        )

        statuses = await hearth_db.get_linked_task_statuses(card_id)
        assert set(statuses) == {"completed", "failed"}

    @pytest.mark.asyncio
    async def test_no_linked_tasks(self):
        card_id = await hearth_db.insert_card(creator="doot", title="No links")
        statuses = await hearth_db.get_linked_task_statuses(card_id)
        assert statuses == []

    @pytest.mark.asyncio
    async def test_ignores_non_task_links(self):
        card_id = await hearth_db.insert_card(
            creator="doot",
            title="Test",
            links=[{"object_type": "morsel", "object_id": "42"}],
        )
        statuses = await hearth_db.get_linked_task_statuses(card_id)
        assert statuses == []
