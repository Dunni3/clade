"""Tests for FTS5 full-text search: database and API layers."""

import os

import pytest
import pytest_asyncio

os.environ.setdefault(
    "MAILBOX_API_KEYS",
    "test-key-doot:doot,test-key-oppy:oppy,test-key-jerry:jerry,test-key-kamaji:kamaji,test-key-ian:ian",
)

from httpx import ASGITransport, AsyncClient

from hearth import db as hearth_db
from hearth.app import app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

DOOT_HEADERS = {"Authorization": "Bearer test-key-doot"}


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


async def _seed_data():
    """Insert some test data for search tests."""
    task_id = await hearth_db.insert_task(
        creator="doot",
        assignee="oppy",
        subject="Deploy the staging server",
        prompt="Run the deploy script for staging environment",
    )
    task_id2 = await hearth_db.insert_task(
        creator="doot",
        assignee="jerry",
        subject="Train the model",
        prompt="Start the GPU training run with config xyz",
    )
    morsel_id = await hearth_db.insert_morsel(
        creator="kamaji",
        body="Conductor tick: deployed staging successfully with zero errors",
        tags=["conductor-tick"],
    )
    card_id = await hearth_db.insert_card(
        creator="doot",
        title="Fix deploy pipeline",
        description="The staging deploy pipeline is broken and needs fixing",
    )
    return {
        "task_ids": [task_id, task_id2],
        "morsel_id": morsel_id,
        "card_id": card_id,
    }


# ---------------------------------------------------------------------------
# Database layer tests
# ---------------------------------------------------------------------------


class TestDatabaseSearch:
    @pytest.mark.asyncio
    async def test_search_tasks_by_subject(self):
        await _seed_data()
        results = await hearth_db.search("staging")
        task_results = [r for r in results if r["type"] == "task"]
        assert len(task_results) >= 1
        assert any("staging" in r["title"].lower() or "staging" in r["snippet"].lower() for r in task_results)

    @pytest.mark.asyncio
    async def test_search_tasks_by_prompt(self):
        await _seed_data()
        results = await hearth_db.search("GPU training")
        task_results = [r for r in results if r["type"] == "task"]
        assert len(task_results) >= 1

    @pytest.mark.asyncio
    async def test_search_morsels_by_body(self):
        await _seed_data()
        results = await hearth_db.search("conductor tick")
        morsel_results = [r for r in results if r["type"] == "morsel"]
        assert len(morsel_results) >= 1

    @pytest.mark.asyncio
    async def test_search_cards_by_title(self):
        await _seed_data()
        results = await hearth_db.search("deploy pipeline")
        card_results = [r for r in results if r["type"] == "card"]
        assert len(card_results) >= 1

    @pytest.mark.asyncio
    async def test_search_cards_by_description(self):
        await _seed_data()
        results = await hearth_db.search("broken")
        card_results = [r for r in results if r["type"] == "card"]
        assert len(card_results) >= 1

    @pytest.mark.asyncio
    async def test_cross_type_search(self):
        """Searching 'deploy*' should find tasks, morsels, and cards via prefix."""
        await _seed_data()
        results = await hearth_db.search("deploy*")
        types_found = set(r["type"] for r in results)
        # deploy* matches "Deploy" in task subject, "deployed" in morsel body, "deploy" in card title
        assert "task" in types_found
        assert "morsel" in types_found
        assert "card" in types_found

    @pytest.mark.asyncio
    async def test_type_filter_task_only(self):
        await _seed_data()
        results = await hearth_db.search("deploy", entity_types=["task"])
        assert all(r["type"] == "task" for r in results)

    @pytest.mark.asyncio
    async def test_type_filter_card_only(self):
        await _seed_data()
        results = await hearth_db.search("deploy", entity_types=["card"])
        assert all(r["type"] == "card" for r in results)

    @pytest.mark.asyncio
    async def test_no_results(self):
        await _seed_data()
        results = await hearth_db.search("xyznonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_limit(self):
        await _seed_data()
        results = await hearth_db.search("deploy", limit=1)
        assert len(results) <= 1

    @pytest.mark.asyncio
    async def test_fts_trigger_on_update(self):
        """Updating a task's output should make it searchable."""
        data = await _seed_data()
        task_id = data["task_ids"][0]
        await hearth_db.update_task(task_id, output="Unique watermark alpha")

        results = await hearth_db.search("watermark alpha")
        assert len(results) >= 1
        assert any(r["id"] == task_id for r in results)

    @pytest.mark.asyncio
    async def test_fts_trigger_on_delete(self):
        """Deleting a card should remove it from the FTS index."""
        data = await _seed_data()
        card_id = data["card_id"]

        # Verify it's searchable first
        results = await hearth_db.search("pipeline")
        assert any(r["type"] == "card" and r["id"] == card_id for r in results)

        await hearth_db.delete_card(card_id)

        results = await hearth_db.search("pipeline")
        assert not any(r["type"] == "card" and r["id"] == card_id for r in results)

    @pytest.mark.asyncio
    async def test_snippets_contain_mark_tags(self):
        await _seed_data()
        results = await hearth_db.search("staging")
        assert len(results) > 0
        assert any("<mark>" in r["snippet"] for r in results)

    @pytest.mark.asyncio
    async def test_created_after_filters(self):
        """created_after excludes older items across all entity types."""
        data = await _seed_data()
        task_id = data["task_ids"][0]
        morsel_id = data["morsel_id"]
        card_id = data["card_id"]

        # Backdate all items to 2025
        db = await hearth_db.get_db()
        await db.execute(
            "UPDATE tasks SET created_at = ? WHERE id = ?",
            ("2025-01-01T00:00:00Z", task_id),
        )
        await db.execute(
            "UPDATE morsels SET created_at = ? WHERE id = ?",
            ("2025-01-01T00:00:00Z", morsel_id),
        )
        await db.execute(
            "UPDATE kanban_cards SET created_at = ? WHERE id = ?",
            ("2025-01-01T00:00:00Z", card_id),
        )
        await db.commit()
        await db.close()

        # Searching with created_after=2026 should exclude all backdated items
        results = await hearth_db.search("deploy*", created_after="2026-01-01T00:00:00Z")
        # The second task (task_id2) still has its original recent timestamp
        # but the first task, morsel, and card are all backdated
        old_ids = {
            ("task", task_id),
            ("morsel", morsel_id),
            ("card", card_id),
        }
        found_ids = {(r["type"], r["id"]) for r in results}
        assert old_ids.isdisjoint(found_ids), "Backdated items should be excluded"

    @pytest.mark.asyncio
    async def test_created_before_filters(self):
        """created_before excludes newer items across all entity types."""
        data = await _seed_data()
        task_id = data["task_ids"][0]

        # All items have recent timestamps by default.
        # Searching with created_before=2020 should exclude everything.
        results = await hearth_db.search("deploy*", created_before="2020-01-01T00:00:00Z")
        assert results == [], "All items are recent and should be excluded by created_before=2020"

        # Backdate one task and verify it IS returned
        db = await hearth_db.get_db()
        await db.execute(
            "UPDATE tasks SET created_at = ? WHERE id = ?",
            ("2019-06-15T00:00:00Z", task_id),
        )
        await db.commit()
        await db.close()

        results = await hearth_db.search(
            "staging", created_before="2020-01-01T00:00:00Z"
        )
        assert len(results) == 1
        assert results[0]["type"] == "task"
        assert results[0]["id"] == task_id

    @pytest.mark.asyncio
    async def test_date_range_combined(self):
        """Both created_after and created_before together form a date range."""
        data = await _seed_data()
        task_id1, task_id2 = data["task_ids"]

        # Put task1 in Jan 2025, task2 in Jun 2025
        db = await hearth_db.get_db()
        await db.execute(
            "UPDATE tasks SET created_at = ? WHERE id = ?",
            ("2025-01-15T00:00:00Z", task_id1),
        )
        await db.execute(
            "UPDATE tasks SET created_at = ? WHERE id = ?",
            ("2025-06-15T00:00:00Z", task_id2),
        )
        await db.commit()
        await db.close()

        # Range that includes only task1 (Jan-Mar 2025)
        results = await hearth_db.search(
            "deploy OR train",
            entity_types=["task"],
            created_after="2025-01-01T00:00:00Z",
            created_before="2025-03-01T00:00:00Z",
        )
        assert len(results) == 1
        assert results[0]["id"] == task_id1

        # Range that includes only task2 (Apr-Aug 2025)
        results = await hearth_db.search(
            "deploy OR train",
            entity_types=["task"],
            created_after="2025-04-01T00:00:00Z",
            created_before="2025-08-01T00:00:00Z",
        )
        assert len(results) == 1
        assert results[0]["id"] == task_id2

        # Range that includes both (Jan-Aug 2025)
        results = await hearth_db.search(
            "deploy OR train",
            entity_types=["task"],
            created_after="2025-01-01T00:00:00Z",
            created_before="2025-08-01T00:00:00Z",
        )
        assert len(results) == 2


# ---------------------------------------------------------------------------
# API layer tests
# ---------------------------------------------------------------------------


class TestAPISearch:
    @pytest.mark.asyncio
    async def test_search_returns_results(self, client):
        await _seed_data()
        resp = await client.get(
            "/api/v1/search", params={"q": "deploy"}, headers=DOOT_HEADERS
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["query"] == "deploy"
        assert len(body["results"]) > 0
        assert body["total"] > 0

    @pytest.mark.asyncio
    async def test_empty_query_returns_422(self, client):
        resp = await client.get(
            "/api/v1/search", params={"q": ""}, headers=DOOT_HEADERS
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_query_returns_422(self, client):
        resp = await client.get("/api/v1/search", headers=DOOT_HEADERS)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_type_filter(self, client):
        await _seed_data()
        resp = await client.get(
            "/api/v1/search",
            params={"q": "deploy", "types": "card"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert all(r["type"] == "card" for r in body["results"])

    @pytest.mark.asyncio
    async def test_invalid_type_returns_422(self, client):
        resp = await client.get(
            "/api/v1/search",
            params={"q": "test", "types": "invalid"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_result_shape(self, client):
        await _seed_data()
        resp = await client.get(
            "/api/v1/search", params={"q": "staging"}, headers=DOOT_HEADERS
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["results"]) > 0
        result = body["results"][0]
        assert "type" in result
        assert "id" in result
        assert "title" in result
        assert "snippet" in result
        assert "rank" in result

    @pytest.mark.asyncio
    async def test_date_filter_params(self, client):
        """API passes created_after and created_before through to db.search."""
        data = await _seed_data()
        task_id = data["task_ids"][0]

        # Backdate the first task to 2025
        db = await hearth_db.get_db()
        await db.execute(
            "UPDATE tasks SET created_at = ? WHERE id = ?",
            ("2025-03-01T00:00:00Z", task_id),
        )
        await db.commit()
        await db.close()

        # With created_after=2026, the backdated task should not appear
        resp = await client.get(
            "/api/v1/search",
            params={
                "q": "staging",
                "types": "task",
                "created_after": "2026-01-01T00:00:00Z",
            },
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert not any(r["id"] == task_id for r in body["results"])

        # With created_before=2026, the backdated task should appear
        resp = await client.get(
            "/api/v1/search",
            params={
                "q": "staging",
                "types": "task",
                "created_before": "2026-01-01T00:00:00Z",
            },
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert any(r["id"] == task_id for r in body["results"])
