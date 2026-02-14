"""Tests for the scientist name pool."""

from clade.cli.naming import SCIENTISTS, format_suggestion, suggest_name


class TestScientists:
    def test_pool_has_entries(self):
        assert len(SCIENTISTS) >= 20

    def test_entries_have_required_keys(self):
        for entry in SCIENTISTS:
            assert "name" in entry
            assert "full" in entry
            assert "bio" in entry

    def test_names_are_lowercase(self):
        for entry in SCIENTISTS:
            assert entry["name"] == entry["name"].lower()

    def test_names_are_unique(self):
        names = [e["name"] for e in SCIENTISTS]
        assert len(names) == len(set(names))


class TestSuggestName:
    def test_returns_dict_with_required_keys(self):
        result = suggest_name()
        assert "name" in result
        assert "full" in result
        assert "bio" in result

    def test_avoids_used_names(self):
        used = [s["name"] for s in SCIENTISTS[:-1]]
        # Only one name left — should always return it
        result = suggest_name(used)
        assert result["name"] == SCIENTISTS[-1]["name"]

    def test_all_used_falls_back_to_full_pool(self):
        all_names = [s["name"] for s in SCIENTISTS]
        result = suggest_name(all_names)
        assert result["name"] in all_names

    def test_empty_used_list(self):
        result = suggest_name([])
        assert result["name"] in [s["name"] for s in SCIENTISTS]

    def test_none_used_list(self):
        result = suggest_name(None)
        assert result["name"] in [s["name"] for s in SCIENTISTS]


class TestFormatSuggestion:
    def test_format(self):
        entry = {"name": "curie", "full": "Marie Curie", "bio": "Pioneered radioactivity research"}
        result = format_suggestion(entry)
        assert "curie" in result
        assert "Marie Curie" in result
        assert "Pioneered radioactivity" in result

    def test_format_structure(self):
        entry = {"name": "test", "full": "Test Person", "bio": "Did stuff"}
        result = format_suggestion(entry)
        assert result == "test (Test Person — Did stuff)"
