from datetime import datetime, timedelta

from fichero_server.workflows.action_library import (
    ActionCategory,
    ActionDefinition,
    ActionLibraryStore,
)


def _action(name: str, *, category=ActionCategory.CUSTOM, tags=None) -> ActionDefinition:
    return ActionDefinition(
        name=name,
        description=f"{name} description",
        category=category,
        tags=tags or [],
        nodes=[{"type": "tool"}],
    )


def test_create_persists_and_reloads_full_action(tmp_path):
    store = ActionLibraryStore(tmp_path)
    created = store.create(_action("Extract names", category=ActionCategory.EXTRACT, tags=["ocr"]))

    reloaded = ActionLibraryStore(tmp_path).get(created.id)

    assert reloaded is not None
    assert reloaded.name == "Extract names"
    assert reloaded.category is ActionCategory.EXTRACT
    assert reloaded.tags == ["ocr"]
    assert reloaded.nodes == [{"type": "tool"}]


def test_update_delete_and_missing_actions(tmp_path):
    store = ActionLibraryStore(tmp_path)
    created = store.create(_action("Original"))

    updated = store.update(created.id, {"name": "Renamed", "tags": ["new"]})

    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.tags == ["new"]
    assert store.update("missing", {"name": "Nope"}) is None
    assert store.delete(created.id) is True
    assert store.get(created.id) is None
    assert not (tmp_path / f"{created.id}.json").exists()
    assert store.delete(created.id) is False


def test_search_filters_and_rankings(tmp_path):
    store = ActionLibraryStore(tmp_path)
    extract = store.create(_action("Extract names", category=ActionCategory.EXTRACT, tags=["ocr", "people"]))
    generate = store.create(_action("Generate summary", category=ActionCategory.GENERATE, tags=["llm"]))
    store.increment_use_count(generate.id)
    store.increment_use_count(generate.id)
    extract.updated_at = datetime.now() - timedelta(days=1)
    store._save_action(extract)

    assert [action.id for action in store.search(query="PEOPLE")] == [extract.id]
    assert [action.id for action in store.search(category=ActionCategory.GENERATE)] == [generate.id]
    assert [action.id for action in store.search(tags=["ocr", "llm"])] == [extract.id, generate.id]
    assert [action.id for action in store.get_popular()] == [generate.id, extract.id]
    assert [action.id for action in store.get_recent()] == [generate.id, extract.id]


def test_export_import_and_invalid_bulk_entry(tmp_path, caplog):
    source = ActionLibraryStore(tmp_path / "source")
    original = source.create(_action("Portable", tags=["shared"]))
    exported = source.export_action(original.id)

    assert exported is not None
    assert "use_count" not in exported
    assert source.export_action("missing") is None

    target = ActionLibraryStore(tmp_path / "target")
    imported = target.import_all([exported, {"name": 42}])

    assert len(imported) == 1
    assert imported[0].id != original.id
    assert imported[0].name == original.name
    assert "Failed to import action" in caplog.text


def test_malformed_saved_file_is_ignored(tmp_path, caplog):
    (tmp_path / "broken.json").write_text("not json")

    store = ActionLibraryStore(tmp_path)

    assert store.list_all() == []
    assert "Failed to load action" in caplog.text
