"""Unit tests for clade migrate CLI helpers."""

import pytest

from clade.cli.migrate_cmd import _resolve_include, _strip_dead_links


class TestResolveInclude:
    def test_default_includes_cards_and_morsels(self):
        result = _resolve_include(None, None)
        assert result == {"cards", "morsels"}

    def test_explicit_include_overrides_default(self):
        result = _resolve_include("cards,morsels,tasks", None)
        assert result == {"cards", "morsels", "tasks"}

    def test_exclude_removes_from_default(self):
        result = _resolve_include(None, "morsels")
        assert result == {"cards"}

    def test_exclude_multiple(self):
        result = _resolve_include(None, "cards,morsels")
        assert result == set()

    def test_never_exports_api_keys(self):
        result = _resolve_include("cards,morsels,api_keys", None)
        assert "api_keys" not in result

    def test_never_exports_ember_registry(self):
        result = _resolve_include("cards,morsels,ember_registry", None)
        assert "ember_registry" not in result

    def test_invalid_table_ignored(self):
        result = _resolve_include("cards,invalid_table", None)
        assert result == {"cards"}

    def test_messages_explicitly_included(self):
        result = _resolve_include("cards,morsels,messages", None)
        assert "messages" in result

    def test_tasks_explicitly_included(self):
        result = _resolve_include("tasks", None)
        assert result == {"tasks"}

    def test_whitespace_stripped(self):
        result = _resolve_include(" cards , morsels ", None)
        assert result == {"cards", "morsels"}


class TestStripDeadLinks:
    def test_strips_task_links_when_tasks_not_exported(self):
        data = {
            "cards": [
                {
                    "id": 1,
                    "title": "My Card",
                    "links": [
                        {"object_type": "task", "object_id": "42"},
                        {"object_type": "morsel", "object_id": "10"},
                    ],
                }
            ],
            "morsels": [{"id": 10, "body": "test"}],
            "tasks": [],
            "messages": [],
        }
        result = _strip_dead_links(data)
        card_links = result["cards"][0]["links"]
        assert len(card_links) == 1
        assert card_links[0]["object_type"] == "morsel"
        assert card_links[0]["object_id"] == "10"

    def test_preserves_morsel_links_when_morsels_exported(self):
        data = {
            "cards": [
                {
                    "id": 1,
                    "links": [{"object_type": "morsel", "object_id": "5"}],
                }
            ],
            "morsels": [{"id": 5, "body": "test"}],
            "tasks": [],
            "messages": [],
        }
        result = _strip_dead_links(data)
        assert len(result["cards"][0]["links"]) == 1

    def test_strips_morsel_links_when_morsel_not_in_export(self):
        data = {
            "cards": [
                {
                    "id": 1,
                    "links": [{"object_type": "morsel", "object_id": "999"}],
                }
            ],
            "morsels": [],
            "tasks": [],
            "messages": [],
        }
        result = _strip_dead_links(data)
        assert result["cards"][0]["links"] == []

    def test_strips_tree_links_always(self):
        data = {
            "cards": [
                {
                    "id": 1,
                    "links": [{"object_type": "tree", "object_id": "7"}],
                }
            ],
            "morsels": [],
            "tasks": [],
            "messages": [],
        }
        result = _strip_dead_links(data)
        assert result["cards"][0]["links"] == []

    def test_preserves_card_to_card_links(self):
        data = {
            "cards": [
                {"id": 1, "links": [{"object_type": "card", "object_id": "2"}]},
                {"id": 2, "links": []},
            ],
            "morsels": [],
            "tasks": [],
            "messages": [],
        }
        result = _strip_dead_links(data)
        assert len(result["cards"][0]["links"]) == 1

    def test_strips_card_link_to_missing_card(self):
        data = {
            "cards": [
                {"id": 1, "links": [{"object_type": "card", "object_id": "999"}]},
            ],
            "morsels": [],
            "tasks": [],
            "messages": [],
        }
        result = _strip_dead_links(data)
        assert result["cards"][0]["links"] == []

    def test_morsel_links_stripped_correctly(self):
        data = {
            "cards": [],
            "morsels": [
                {
                    "id": 1,
                    "body": "test",
                    "links": [
                        {"object_type": "task", "object_id": "5"},
                        {"object_type": "card", "object_id": "2"},
                    ],
                }
            ],
            "tasks": [],
            "messages": [],
        }
        result = _strip_dead_links(data)
        # task link stripped (no tasks), card link stripped (card 2 not in export)
        assert result["morsels"][0]["links"] == []

    def test_preserves_message_links_when_messages_included(self):
        data = {
            "cards": [
                {"id": 1, "links": [{"object_type": "message", "object_id": "3"}]},
            ],
            "morsels": [],
            "tasks": [],
            "messages": [{"id": 3, "body": "hi"}],
        }
        result = _strip_dead_links(data)
        assert len(result["cards"][0]["links"]) == 1

    def test_no_links_field_no_crash(self):
        data = {
            "cards": [{"id": 1, "title": "No links key"}],
            "morsels": [],
            "tasks": [],
            "messages": [],
        }
        result = _strip_dead_links(data)
        assert result["cards"][0].get("links", []) == []
