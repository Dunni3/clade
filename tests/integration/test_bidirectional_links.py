"""Tests for bidirectional cross-object links (card #25).

When a link is created between two objects that both have link tables
(cards and morsels), the reverse link should be automatically created.
"""

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
# Database layer: morsel → card creates card → morsel reverse
# ---------------------------------------------------------------------------


class TestMorselToCardReverse:
    @pytest.mark.asyncio
    async def test_morsel_card_link_creates_reverse(self):
        """Creating a morsel with a card link should auto-create the reverse card→morsel link."""
        card_id = await hearth_db.insert_card(creator="doot", title="Test card")
        morsel_id = await hearth_db.insert_morsel(
            creator="oppy",
            body="Observation about card",
            links=[{"object_type": "card", "object_id": str(card_id)}],
        )

        # Morsel should have the card link
        morsel = await hearth_db.get_morsel(morsel_id)
        assert any(
            l["object_type"] == "card" and l["object_id"] == str(card_id)
            for l in morsel["links"]
        )

        # Card should now have the reverse morsel link
        card = await hearth_db.get_card(card_id)
        assert any(
            l["object_type"] == "morsel" and l["object_id"] == str(morsel_id)
            for l in card["links"]
        )

    @pytest.mark.asyncio
    async def test_morsel_card_link_no_duplicate(self):
        """If the reverse link already exists, no duplicate should be created."""
        card_id = await hearth_db.insert_card(creator="doot", title="Test card")

        # First morsel with card link
        morsel_id = await hearth_db.insert_morsel(
            creator="oppy",
            body="First observation",
            links=[{"object_type": "card", "object_id": str(card_id)}],
        )

        # Manually add the same reverse link (should already exist)
        card = await hearth_db.get_card(card_id)
        morsel_links = [
            l for l in card["links"]
            if l["object_type"] == "morsel" and l["object_id"] == str(morsel_id)
        ]
        assert len(morsel_links) == 1  # Exactly one, not duplicated

    @pytest.mark.asyncio
    async def test_morsel_nonlinkable_target_no_reverse(self):
        """A morsel linking to a task should not create a reverse link (tasks have no link table)."""
        morsel_id = await hearth_db.insert_morsel(
            creator="oppy",
            body="About task 42",
            links=[{"object_type": "task", "object_id": "42"}],
        )
        morsel = await hearth_db.get_morsel(morsel_id)
        assert len(morsel["links"]) == 1
        assert morsel["links"][0]["object_type"] == "task"
        # No error, just no reverse — tasks don't have link tables


# ---------------------------------------------------------------------------
# Database layer: card → morsel creates morsel → card reverse
# ---------------------------------------------------------------------------


class TestCardToMorselReverse:
    @pytest.mark.asyncio
    async def test_card_morsel_link_creates_reverse(self):
        """Creating a card with a morsel link should auto-create the reverse morsel→card link."""
        morsel_id = await hearth_db.insert_morsel(
            creator="oppy", body="Some observation"
        )
        card_id = await hearth_db.insert_card(
            creator="doot",
            title="Card linking to morsel",
            links=[{"object_type": "morsel", "object_id": str(morsel_id)}],
        )

        # Card should have the morsel link
        card = await hearth_db.get_card(card_id)
        assert any(
            l["object_type"] == "morsel" and l["object_id"] == str(morsel_id)
            for l in card["links"]
        )

        # Morsel should now have the reverse card link
        morsel = await hearth_db.get_morsel(morsel_id)
        assert any(
            l["object_type"] == "card" and l["object_id"] == str(card_id)
            for l in morsel["links"]
        )

    @pytest.mark.asyncio
    async def test_card_nonlinkable_target_no_reverse(self):
        """A card linking to a task should not create a reverse link."""
        card_id = await hearth_db.insert_card(
            creator="doot",
            title="Card with task link",
            links=[{"object_type": "task", "object_id": "99"}],
        )
        card = await hearth_db.get_card(card_id)
        assert len(card["links"]) == 1


# ---------------------------------------------------------------------------
# Database layer: card → card creates reverse card → card
# ---------------------------------------------------------------------------


class TestCardToCardReverse:
    @pytest.mark.asyncio
    async def test_card_card_link_creates_reverse(self):
        """Creating a card that links to another card should auto-create the reverse."""
        card_a = await hearth_db.insert_card(creator="doot", title="Card A")
        card_b = await hearth_db.insert_card(
            creator="doot",
            title="Card B",
            links=[{"object_type": "card", "object_id": str(card_a)}],
        )

        # Card B links to Card A
        b = await hearth_db.get_card(card_b)
        assert any(
            l["object_type"] == "card" and l["object_id"] == str(card_a)
            for l in b["links"]
        )

        # Card A should now link back to Card B
        a = await hearth_db.get_card(card_a)
        assert any(
            l["object_type"] == "card" and l["object_id"] == str(card_b)
            for l in a["links"]
        )


# ---------------------------------------------------------------------------
# Database layer: update_card replaces links, manages reverse links
# ---------------------------------------------------------------------------


class TestUpdateCardReverseLinks:
    @pytest.mark.asyncio
    async def test_update_card_adds_reverse_links(self):
        """Updating a card to add a morsel link should create the reverse."""
        morsel_id = await hearth_db.insert_morsel(
            creator="oppy", body="Observation"
        )
        card_id = await hearth_db.insert_card(creator="doot", title="Test")

        await hearth_db.update_card(
            card_id,
            links=[{"object_type": "morsel", "object_id": str(morsel_id)}],
        )

        morsel = await hearth_db.get_morsel(morsel_id)
        assert any(
            l["object_type"] == "card" and l["object_id"] == str(card_id)
            for l in morsel["links"]
        )

    @pytest.mark.asyncio
    async def test_update_card_removes_old_reverse_links(self):
        """Replacing card links should remove old reverse links."""
        morsel_a = await hearth_db.insert_morsel(creator="oppy", body="Morsel A")
        morsel_b = await hearth_db.insert_morsel(creator="oppy", body="Morsel B")

        card_id = await hearth_db.insert_card(
            creator="doot",
            title="Test",
            links=[{"object_type": "morsel", "object_id": str(morsel_a)}],
        )

        # Morsel A should have reverse link
        morsel = await hearth_db.get_morsel(morsel_a)
        assert any(
            l["object_type"] == "card" and l["object_id"] == str(card_id)
            for l in morsel["links"]
        )

        # Now update card to link to morsel B instead
        await hearth_db.update_card(
            card_id,
            links=[{"object_type": "morsel", "object_id": str(morsel_b)}],
        )

        # Morsel A should no longer have the reverse link
        morsel_a_data = await hearth_db.get_morsel(morsel_a)
        assert not any(
            l["object_type"] == "card" and l["object_id"] == str(card_id)
            for l in morsel_a_data["links"]
        )

        # Morsel B should have the reverse link
        morsel_b_data = await hearth_db.get_morsel(morsel_b)
        assert any(
            l["object_type"] == "card" and l["object_id"] == str(card_id)
            for l in morsel_b_data["links"]
        )

    @pytest.mark.asyncio
    async def test_update_card_clear_links_removes_reverse(self):
        """Clearing all card links should remove reverse links."""
        morsel_id = await hearth_db.insert_morsel(creator="oppy", body="Test")
        card_id = await hearth_db.insert_card(
            creator="doot",
            title="Test",
            links=[{"object_type": "morsel", "object_id": str(morsel_id)}],
        )

        # Reverse link exists
        morsel = await hearth_db.get_morsel(morsel_id)
        assert len(morsel["links"]) == 1

        # Clear links
        await hearth_db.update_card(card_id, links=[])

        # Reverse link should be gone
        morsel = await hearth_db.get_morsel(morsel_id)
        assert len(morsel["links"]) == 0


# ---------------------------------------------------------------------------
# Database layer: delete_card cleans up reverse links
# ---------------------------------------------------------------------------


class TestDeleteCardReverseLinks:
    @pytest.mark.asyncio
    async def test_delete_card_removes_reverse_links(self):
        """Deleting a card should remove its reverse links from linked objects."""
        morsel_id = await hearth_db.insert_morsel(creator="oppy", body="Test")
        card_id = await hearth_db.insert_card(
            creator="doot",
            title="Doomed card",
            links=[{"object_type": "morsel", "object_id": str(morsel_id)}],
        )

        # Reverse link exists
        morsel = await hearth_db.get_morsel(morsel_id)
        assert any(
            l["object_type"] == "card" and l["object_id"] == str(card_id)
            for l in morsel["links"]
        )

        # Delete the card
        await hearth_db.delete_card(card_id)

        # Reverse link should be gone
        morsel = await hearth_db.get_morsel(morsel_id)
        assert not any(
            l["object_type"] == "card" and l["object_id"] == str(card_id)
            for l in morsel["links"]
        )


# ---------------------------------------------------------------------------
# API layer: morsel creation with card link
# ---------------------------------------------------------------------------


class TestAPIBidirectionalLinks:
    @pytest.mark.asyncio
    async def test_create_morsel_with_card_link_creates_reverse(self, client):
        """POST /morsels with a card link should create the card→morsel reverse link."""
        # Create a card first
        card_resp = await client.post(
            "/api/v1/kanban/cards",
            json={"title": "API card"},
            headers=DOOT_HEADERS,
        )
        card_id = card_resp.json()["id"]

        # Create morsel linking to card
        morsel_resp = await client.post(
            "/api/v1/morsels",
            json={
                "body": "API morsel observation",
                "links": [{"object_type": "card", "object_id": str(card_id)}],
            },
            headers=OPPY_HEADERS,
        )
        assert morsel_resp.status_code == 201
        morsel_id = morsel_resp.json()["id"]

        # Check card now has reverse link
        card_detail = await client.get(
            f"/api/v1/kanban/cards/{card_id}",
            headers=DOOT_HEADERS,
        )
        card_data = card_detail.json()
        assert any(
            l["object_type"] == "morsel" and l["object_id"] == str(morsel_id)
            for l in card_data["links"]
        )

    @pytest.mark.asyncio
    async def test_create_card_with_morsel_link_creates_reverse(self, client):
        """POST /kanban/cards with a morsel link should create the morsel→card reverse link."""
        # Create morsel first
        morsel_resp = await client.post(
            "/api/v1/morsels",
            json={"body": "API morsel"},
            headers=OPPY_HEADERS,
        )
        morsel_id = morsel_resp.json()["id"]

        # Create card linking to morsel
        card_resp = await client.post(
            "/api/v1/kanban/cards",
            json={
                "title": "API card with morsel link",
                "links": [{"object_type": "morsel", "object_id": str(morsel_id)}],
            },
            headers=DOOT_HEADERS,
        )
        assert card_resp.status_code == 201
        card_id = card_resp.json()["id"]

        # Check morsel now has reverse link
        morsel_detail = await client.get(
            f"/api/v1/morsels/{morsel_id}",
            headers=DOOT_HEADERS,
        )
        morsel_data = morsel_detail.json()
        assert any(
            l["object_type"] == "card" and l["object_id"] == str(card_id)
            for l in morsel_data["links"]
        )

    @pytest.mark.asyncio
    async def test_update_card_links_creates_reverse(self, client):
        """PATCH /kanban/cards/{id} with new links should create reverse links."""
        morsel_resp = await client.post(
            "/api/v1/morsels",
            json={"body": "API morsel for update"},
            headers=OPPY_HEADERS,
        )
        morsel_id = morsel_resp.json()["id"]

        card_resp = await client.post(
            "/api/v1/kanban/cards",
            json={"title": "API card for update"},
            headers=DOOT_HEADERS,
        )
        card_id = card_resp.json()["id"]

        # Update card to link to morsel
        await client.patch(
            f"/api/v1/kanban/cards/{card_id}",
            json={"links": [{"object_type": "morsel", "object_id": str(morsel_id)}]},
            headers=DOOT_HEADERS,
        )

        # Check morsel has reverse link
        morsel_detail = await client.get(
            f"/api/v1/morsels/{morsel_id}",
            headers=DOOT_HEADERS,
        )
        morsel_data = morsel_detail.json()
        assert any(
            l["object_type"] == "card" and l["object_id"] == str(card_id)
            for l in morsel_data["links"]
        )

    @pytest.mark.asyncio
    async def test_card_to_card_link_creates_reverse_via_api(self, client):
        """Creating a card linking to another card via API should create the reverse."""
        card_a_resp = await client.post(
            "/api/v1/kanban/cards",
            json={"title": "Card A"},
            headers=DOOT_HEADERS,
        )
        card_a_id = card_a_resp.json()["id"]

        card_b_resp = await client.post(
            "/api/v1/kanban/cards",
            json={
                "title": "Card B",
                "links": [{"object_type": "card", "object_id": str(card_a_id)}],
            },
            headers=DOOT_HEADERS,
        )
        card_b_id = card_b_resp.json()["id"]

        # Card A should link back to Card B
        card_a_detail = await client.get(
            f"/api/v1/kanban/cards/{card_a_id}",
            headers=DOOT_HEADERS,
        )
        card_a_data = card_a_detail.json()
        assert any(
            l["object_type"] == "card" and l["object_id"] == str(card_b_id)
            for l in card_a_data["links"]
        )
