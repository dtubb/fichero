"""`document_parents` on the change event (#4205).

Every imported document was being appended to `collections`, a roots-only
list. The client fix is "only fetch a document if it's a root, is in the
selected collection, or has a parent already loaded" — O(on-screen) instead of
O(imported), which is the 100k-file case. That filter is impossible without a
parent on the event: `parentId` was unknowable until after the `getDocument`
call the filter exists to avoid.

A per-id MAP rather than a single `parent_id`, because `document_ids` is a
list whose entries can have different parents. A scalar would be correct only
for single-document events and silently wrong otherwise.

The contract these pin: an id ABSENT from the map means "parent unknown, fetch
it" and NEVER "this is a root". Absence-as-root would file imported documents
at the top level — the very bug being fixed.
"""

from __future__ import annotations

from fichero.api.change_stream import ChangeEvent


class TestContract:
    def test_defaults_to_empty_so_the_field_is_additive(self):
        """Existing emitters keep working untouched."""
        event = ChangeEvent(type="document.created", document_ids=["d1"])

        assert event.document_parents == {}

    def test_a_partial_map_is_safe_by_construction(self):
        """One known parent, one unknown — the unknown is simply absent.

        This is the shape a bulk emitter produces, and it must not require the
        emitter to invent a value for the ids it cannot resolve.
        """
        event = ChangeEvent(
            type="document.created",
            document_ids=["known", "unknown"],
            document_parents={"known": "folder-1"},
        )

        assert event.document_parents["known"] == "folder-1"
        assert "unknown" not in event.document_parents

    def test_distinct_parents_survive_in_one_event(self):
        """The reason this is a map: one event, several parents."""
        event = ChangeEvent(
            type="document.created",
            document_ids=["a", "b"],
            document_parents={"a": "folder-1", "b": "folder-2"},
        )

        assert event.document_parents == {"a": "folder-1", "b": "folder-2"}

    def test_the_contract_is_documented_in_the_generated_schema(self):
        """The 'absent != root' rule has to reach the Swift client's docs.

        The client reads absence; if that reaches swift-lane as an undocumented
        empty dict, absence-as-root is the natural (wrong) reading.
        """
        description = ChangeEvent.model_fields["document_parents"].description or ""

        assert "NEVER means 'this is a root'" in description
        assert "FETCH IT" in description


class TestEmitChangeThreadsItThrough:
    def test_emit_change_forwards_the_map(self, monkeypatch):
        from fichero.api import change_stream

        captured: list[ChangeEvent] = []
        monkeypatch.setattr(
            change_stream._change_hub,
            "emit",
            lambda library_path, event: captured.append(event),
        )

        change_stream.emit_change(
            "/tmp/lib",
            type="document.created",
            document_ids=["d1"],
            document_parents={"d1": "folder-1"},
        )

        assert captured, "emit_change did not reach the hub"
        assert captured[0].document_parents == {"d1": "folder-1"}

    def test_emit_change_without_the_map_still_works(self, monkeypatch):
        """Every other call site passes nothing — they must be unaffected."""
        from fichero.api import change_stream

        captured: list[ChangeEvent] = []
        monkeypatch.setattr(
            change_stream._change_hub,
            "emit",
            lambda library_path, event: captured.append(event),
        )

        change_stream.emit_change("/tmp/lib", type="entity.updated", entity_ids=["e1"])

        assert captured[0].document_parents == {}


class TestImportPopulatesIt:
    """The requirement: a real import emits the map POPULATED.

    Asserting only that the field exists would pass against an emitter that
    never fills it — which is the whole failure being fixed.
    """

    def test_import_file_action_carries_the_parent(self, monkeypatch, tmp_path):
        from fichero.api.routes.ingest import core
        from fichero.models import Document

        doc = Document(name="scan.jpg", parent_id="folder-1")
        monkeypatch.setattr(core, "import_file_impl", lambda db, params, path: doc)

        class _Ctx:
            library_path = str(tmp_path)

        class _DB:
            path = str(tmp_path / "lib.duckdb")

        _payload, spec = core._action_import_file(_DB(), object(), _Ctx())

        assert spec.document_ids == [doc.id]
        assert spec.document_parents == {doc.id: "folder-1"}, (
            "the import action knows the parent and must publish it, or the "
            "client is forced to fetch every imported document"
        )

    def test_folder_import_bulk_event_also_carries_parents(self, monkeypatch, tmp_path):
        """The trailing bulk event repeats every id from the import.

        Without parents on it, the client would treat all of them as "unknown,
        fetch it" and re-flood itself with exactly the fetches the per-file
        events let it skip — the optimisation would survive the stream and then
        die at the end. The Documents are in hand here, so parents are free.
        """
        from fichero.api.routes.ingest import core
        from fichero.models import Document

        docs = [
            Document(name="a.jpg", parent_id="folder-1"),
            Document(name="b.jpg", parent_id="folder-2"),
            Document(name="root.jpg", parent_id=None),
        ]
        monkeypatch.setattr(core, "import_folder_impl", lambda *a, **k: docs)

        class _Ctx:
            library_path = str(tmp_path)
            on_progress = None
            on_document = None
            should_cancel = None

        class _DB:
            path = str(tmp_path / "lib.duckdb")

        _payload, spec = core._action_import_folder(_DB(), object(), _Ctx())

        assert spec.document_ids == [d.id for d in docs]
        assert spec.document_parents == {docs[0].id: "folder-1", docs[1].id: "folder-2"}
        # The parentless one is absent, not recorded as a root.
        assert docs[2].id not in spec.document_parents

    def test_a_root_document_is_omitted_not_marked_root(self, monkeypatch, tmp_path):
        """parent_id None -> NO entry. Never an entry meaning 'root'."""
        from fichero.api.routes.ingest import core
        from fichero.models import Document

        doc = Document(name="top-level.jpg", parent_id=None)
        monkeypatch.setattr(core, "import_file_impl", lambda db, params, path: doc)

        class _Ctx:
            library_path = str(tmp_path)

        class _DB:
            path = str(tmp_path / "lib.duckdb")

        _payload, spec = core._action_import_file(_DB(), object(), _Ctx())

        assert spec.document_parents == {}
