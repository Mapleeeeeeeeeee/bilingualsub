"""Tests for GlossaryManager."""

import pytest

from bilingualsub.core.glossary import GlossaryEntry, GlossaryError, GlossaryManager


@pytest.mark.unit
class TestGlossaryManager:
    def test_add_and_get_all(self, tmp_path):
        manager = GlossaryManager(tmp_path / "glossary.json")
        entry = manager.add("Agent", "Agent")
        assert entry == GlossaryEntry(source="Agent", target="Agent")
        assert manager.get_all() == [entry]

    def test_add_strips_whitespace(self, tmp_path):
        manager = GlossaryManager(tmp_path / "glossary.json")
        entry = manager.add("  Agent  ", "  Agent  ")
        assert entry.source == "Agent"
        assert entry.target == "Agent"

    def test_add_empty_source_raises(self, tmp_path):
        manager = GlossaryManager(tmp_path / "glossary.json")
        with pytest.raises(GlossaryError, match="cannot be empty"):
            manager.add("", "target")

    def test_add_duplicate_upserts(self, tmp_path):
        manager = GlossaryManager(tmp_path / "glossary.json")
        manager.add("Agent", "Agent")
        updated = manager.add("Agent", "代理")
        assert updated.target == "代理"
        assert len(manager.get_all()) == 1

    def test_add_over_max_length_raises(self, tmp_path):
        manager = GlossaryManager(tmp_path / "glossary.json")
        with pytest.raises(GlossaryError, match="cannot exceed"):
            manager.add("x" * 101, "target")

    def test_add_over_max_entries_raises(self, tmp_path):
        manager = GlossaryManager(tmp_path / "glossary.json")
        for i in range(500):
            manager.add(f"term{i:04d}", f"value{i}")
        with pytest.raises(GlossaryError, match="full"):
            manager.add("one_too_many", "value")

    def test_update_existing(self, tmp_path):
        manager = GlossaryManager(tmp_path / "glossary.json")
        manager.add("Agent", "Agent")
        updated = manager.update("Agent", "代理")
        assert updated.target == "代理"

    def test_update_nonexistent_raises(self, tmp_path):
        manager = GlossaryManager(tmp_path / "glossary.json")
        with pytest.raises(GlossaryError, match="not found"):
            manager.update("nope", "value")

    def test_delete_existing(self, tmp_path):
        manager = GlossaryManager(tmp_path / "glossary.json")
        manager.add("Agent", "Agent")
        manager.delete("Agent")
        assert manager.get_all() == []

    def test_delete_nonexistent_raises(self, tmp_path):
        manager = GlossaryManager(tmp_path / "glossary.json")
        with pytest.raises(GlossaryError, match="not found"):
            manager.delete("nope")

    def test_persistence_round_trip(self, tmp_path):
        path = tmp_path / "glossary.json"
        manager1 = GlossaryManager(path)
        manager1.add("Agent", "Agent")
        manager1.add("Skills", "Skills")

        manager2 = GlossaryManager(path)
        entries = manager2.get_all()
        assert len(entries) == 2
        sources = [e.source for e in entries]
        assert "Agent" in sources
        assert "Skills" in sources

    def test_corrupted_json_creates_backup(self, tmp_path):
        path = tmp_path / "glossary.json"
        path.write_text("{invalid json", encoding="utf-8")
        manager = GlossaryManager(path)
        assert manager.get_all() == []
        assert path.with_suffix(".json.bak").exists()

    def test_format_for_prompt_empty(self, tmp_path):
        manager = GlossaryManager(tmp_path / "glossary.json")
        assert manager.format_for_prompt() == ""

    def test_format_for_prompt_with_entries(self, tmp_path):
        manager = GlossaryManager(tmp_path / "glossary.json")
        manager.add("Agent", "Agent")
        manager.add("Skills", "Skills")
        prompt = manager.format_for_prompt()
        assert "Agent → Agent" in prompt
        assert "Skills → Skills" in prompt
        assert "術語表" in prompt

    def test_format_for_prompt_reflects_mutations(self, tmp_path):
        manager = GlossaryManager(tmp_path / "glossary.json")
        manager.add("Agent", "Agent")
        prompt_before = manager.format_for_prompt()
        assert "Agent" in prompt_before
        assert "Skills" not in prompt_before
        manager.add("Skills", "Skills")
        prompt_after = manager.format_for_prompt()
        assert "Skills" in prompt_after

    def test_nonexistent_file_starts_empty(self, tmp_path):
        manager = GlossaryManager(tmp_path / "nonexistent" / "glossary.json")
        assert manager.get_all() == []

    def test_get_all_sorted_case_insensitive(self, tmp_path):
        manager = GlossaryManager(tmp_path / "glossary.json")
        manager.add("Zebra", "Zebra")
        manager.add("agent", "agent")
        manager.add("Alpha", "Alpha")
        entries = manager.get_all()
        assert [e.source for e in entries] == ["agent", "Alpha", "Zebra"]
