"""Tests for the morsel system: database and API."""

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
# Morsels — database layer
# ---------------------------------------------------------------------------


class TestDatabaseMorsels:
    @pytest.mark.asyncio
    async def test_insert_and_get(self):
        morsel_id = await hearth_db.insert_morsel(
            creator="oppy", body="Found a bug in the auth module"
        )
        assert morsel_id > 0

        morsel = await hearth_db.get_morsel(morsel_id)
        assert morsel is not None
        assert morsel["creator"] == "oppy"
        assert morsel["body"] == "Found a bug in the auth module"
        assert morsel["tags"] == []
        assert morsel["links"] == []

    @pytest.mark.asyncio
    async def test_insert_with_tags(self):
        morsel_id = await hearth_db.insert_morsel(
            creator="oppy",
            body="Performance regression detected",
            tags=["bug", "performance"],
        )
        morsel = await hearth_db.get_morsel(morsel_id)
        assert set(morsel["tags"]) == {"bug", "performance"}

    @pytest.mark.asyncio
    async def test_insert_with_links(self):
        morsel_id = await hearth_db.insert_morsel(
            creator="oppy",
            body="Related to task 42",
            links=[
                {"object_type": "task", "object_id": "42"},
                {"object_type": "brother", "object_id": "jerry"},
            ],
        )
        morsel = await hearth_db.get_morsel(morsel_id)
        assert len(morsel["links"]) == 2
        link_tuples = {(l["object_type"], l["object_id"]) for l in morsel["links"]}
        assert ("task", "42") in link_tuples
        assert ("brother", "jerry") in link_tuples

    @pytest.mark.asyncio
    async def test_get_morsel_not_found(self):
        morsel = await hearth_db.get_morsel(999)
        assert morsel is None

    @pytest.mark.asyncio
    async def test_filter_by_creator(self):
        await hearth_db.insert_morsel(creator="oppy", body="From oppy")
        await hearth_db.insert_morsel(creator="jerry", body="From jerry")

        morsels = await hearth_db.get_morsels(creator="oppy")
        assert len(morsels) == 1
        assert morsels[0]["creator"] == "oppy"

    @pytest.mark.asyncio
    async def test_filter_by_tag(self):
        await hearth_db.insert_morsel(creator="oppy", body="Tagged", tags=["important"])
        await hearth_db.insert_morsel(creator="oppy", body="Not tagged")

        morsels = await hearth_db.get_morsels(tag="important")
        assert len(morsels) == 1
        assert morsels[0]["body"] == "Tagged"

    @pytest.mark.asyncio
    async def test_filter_by_link(self):
        await hearth_db.insert_morsel(
            creator="oppy", body="Linked",
            links=[{"object_type": "task", "object_id": "5"}],
        )
        await hearth_db.insert_morsel(creator="oppy", body="Not linked")

        morsels = await hearth_db.get_morsels(object_type="task", object_id="5")
        assert len(morsels) == 1
        assert morsels[0]["body"] == "Linked"

    @pytest.mark.asyncio
    async def test_pagination(self):
        for i in range(5):
            await hearth_db.insert_morsel(creator="oppy", body=f"Morsel {i}")

        page1 = await hearth_db.get_morsels(limit=2, offset=0)
        assert len(page1) == 2

        page2 = await hearth_db.get_morsels(limit=2, offset=2)
        assert len(page2) == 2

        page3 = await hearth_db.get_morsels(limit=2, offset=4)
        assert len(page3) == 1

    @pytest.mark.asyncio
    async def test_bulk_tags_and_links(self):
        """Tags and links are bulk-fetched for list queries."""
        m1 = await hearth_db.insert_morsel(
            creator="oppy", body="M1", tags=["a", "b"],
            links=[{"object_type": "task", "object_id": "1"}],
        )
        m2 = await hearth_db.insert_morsel(
            creator="oppy", body="M2", tags=["c"],
        )

        morsels = await hearth_db.get_morsels()
        assert len(morsels) == 2
        # Both morsels should have their tags/links populated regardless of order
        by_body = {m["body"]: m for m in morsels}
        assert set(by_body["M1"]["tags"]) == {"a", "b"}
        assert len(by_body["M1"]["links"]) == 1
        assert set(by_body["M2"]["tags"]) == {"c"}
        assert by_body["M2"]["links"] == []


# ---------------------------------------------------------------------------
# Morsels — API endpoints
# ---------------------------------------------------------------------------


class TestAPIMorsels:
    @pytest.mark.asyncio
    async def test_create_morsel(self, client):
        resp = await client.post(
            "/api/v1/morsels",
            json={"body": "An observation"},
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["creator"] == "doot"
        assert data["body"] == "An observation"
        assert data["tags"] == []
        assert data["links"] == []

    @pytest.mark.asyncio
    async def test_create_morsel_with_tags_and_links(self, client):
        resp = await client.post(
            "/api/v1/morsels",
            json={
                "body": "Detailed observation",
                "tags": ["important", "bug"],
                "links": [
                    {"object_type": "task", "object_id": "42"},
                ],
            },
            headers=OPPY_HEADERS,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["creator"] == "oppy"
        assert set(data["tags"]) == {"important", "bug"}
        assert len(data["links"]) == 1
        assert data["links"][0]["object_type"] == "task"
        assert data["links"][0]["object_id"] == "42"

    @pytest.mark.asyncio
    async def test_list_morsels(self, client):
        await client.post(
            "/api/v1/morsels",
            json={"body": "First"},
            headers=DOOT_HEADERS,
        )
        await client.post(
            "/api/v1/morsels",
            json={"body": "Second"},
            headers=OPPY_HEADERS,
        )

        resp = await client.get("/api/v1/morsels", headers=DOOT_HEADERS)
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    @pytest.mark.asyncio
    async def test_list_morsels_filter_creator(self, client):
        await client.post(
            "/api/v1/morsels",
            json={"body": "By doot"},
            headers=DOOT_HEADERS,
        )
        await client.post(
            "/api/v1/morsels",
            json={"body": "By oppy"},
            headers=OPPY_HEADERS,
        )

        resp = await client.get(
            "/api/v1/morsels",
            params={"creator": "doot"},
            headers=DOOT_HEADERS,
        )
        morsels = resp.json()
        assert len(morsels) == 1
        assert morsels[0]["creator"] == "doot"

    @pytest.mark.asyncio
    async def test_list_morsels_filter_tag(self, client):
        await client.post(
            "/api/v1/morsels",
            json={"body": "Tagged", "tags": ["special"]},
            headers=DOOT_HEADERS,
        )
        await client.post(
            "/api/v1/morsels",
            json={"body": "Untagged"},
            headers=DOOT_HEADERS,
        )

        resp = await client.get(
            "/api/v1/morsels",
            params={"tag": "special"},
            headers=DOOT_HEADERS,
        )
        morsels = resp.json()
        assert len(morsels) == 1
        assert morsels[0]["body"] == "Tagged"

    @pytest.mark.asyncio
    async def test_get_morsel_detail(self, client):
        resp = await client.post(
            "/api/v1/morsels",
            json={"body": "Detail test", "tags": ["x"]},
            headers=DOOT_HEADERS,
        )
        morsel_id = resp.json()["id"]

        resp = await client.get(
            f"/api/v1/morsels/{morsel_id}",
            headers=DOOT_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["body"] == "Detail test"
        assert data["tags"] == ["x"]

    @pytest.mark.asyncio
    async def test_get_morsel_not_found(self, client):
        resp = await client.get("/api/v1/morsels/999", headers=DOOT_HEADERS)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_morsel_no_auth(self, client):
        resp = await client.post(
            "/api/v1/morsels",
            json={"body": "No auth"},
        )
        assert resp.status_code == 422
