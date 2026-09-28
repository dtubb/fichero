"""The two predicates that decide whether a machine may overwrite a page's text.

The end-to-end tests (`test_segment_corrections_survive_a_rerun.py`) prove these are CALLED; these
prove they are RIGHT. A wrong answer here is a rerun replacing someone's transcription.
"""
from types import SimpleNamespace

from fichero_server.workflows.curation_guard import (
    PAGE_CONTENT_USER_EDITED_KEY,
    page_content_is_user_edited,
    page_text_is_derived,
)


class TestPageContentIsUserEdited:
    def test_true_when_a_person_saved_an_edit(self):
        doc = SimpleNamespace(metadata={PAGE_CONTENT_USER_EDITED_KEY: "2026-09-26T00:00:00Z"})
        assert page_content_is_user_edited(doc) is True

    def test_false_without_the_flag_or_without_metadata(self):
        assert page_content_is_user_edited(SimpleNamespace(metadata={})) is False
        assert page_content_is_user_edited(SimpleNamespace(metadata=None)) is False
        assert page_content_is_user_edited(SimpleNamespace()) is False


class TestPageTextIsDerived:
    def test_false_for_a_page_nobody_has_edited(self, db):
        from tests.unit.api.seeded_converted_page import seed_page as seed
        _, page, _ = seed(db)
        assert page_text_is_derived(db, page.id) is False

    def test_true_once_a_result_has_become_segment_rows(self, db, client):
        from tests.unit.api.seeded_converted_page import seed_page as seed
        _, page, art = seed(db)
        r = client.put(f"/api/artifacts/{art.id}/regions", json={"op": "move", "indices": [1], "bbox": [0.5, 0.5, 0.3, 0.05]})
        assert r.status_code == 200
        assert page_text_is_derived(db, page.id) is True

    def test_false_for_a_document_with_no_artifacts(self, db):
        assert page_text_is_derived(db, "no-such-document") is False


class TestConvertedByTheEngineIsNotAPersonsWork:
    """#5222: the engine converts every page when a library opens. A page it converted is still
    the machine's to write, so a later transcription reaches page_content, search and the Reader;
    only a PERSON's mark on the page model makes its text derived. If this regresses, opening a
    library freezes every page's text against every later run."""

    @staticmethod
    def _converted_by_the_engine(db):
        import fichero_server.api.main  # noqa: F401  (registers every action)
        from fichero_server.actions.registry import ActionContext, registry
        from tests.unit.api.seeded_converted_page import seed_page as seed

        _, page, _ = seed(db)
        engine = ActionContext(actor="system", is_bootstrap=True)
        registry.invoke(db, "segment.convert_and_edit", {"document_id": page.id}, engine)
        return page

    @staticmethod
    def _person():
        from fichero_server.actions.registry import ActionContext

        return ActionContext(actor="historian", is_bootstrap=True)

    def test_a_page_the_engine_converted_is_not_derived(self, db):
        page = self._converted_by_the_engine(db)
        assert page_text_is_derived(db, page.id) is False

    def test_a_persons_correction_of_a_reading_makes_it_derived(self, db):
        from fichero_server.actions.registry import registry
        from fichero_server.models import ContentRepresentation

        page = self._converted_by_the_engine(db)
        reading = db.query(ContentRepresentation, document_id=page.id)[0]
        registry.invoke(db, "representation.revise",
                        {"representation_id": reading.id, "content": "In the yeere"}, self._person())
        assert page_text_is_derived(db, page.id) is True

    def test_a_person_deleting_a_line_makes_it_derived(self, db):
        from fichero_server.actions.registry import registry
        from fichero_server.models import Segment

        page = self._converted_by_the_engine(db)
        line = next(s for s in db.query(Segment, document_id=page.id) if s.kind == "line")
        registry.invoke(db, "segment.delete",
                        {"segment_ids": [line.id], "expected_versions": {line.id: line.version}},
                        self._person())
        assert page_text_is_derived(db, page.id) is True

    def test_a_person_choosing_the_working_pass_makes_it_derived(self, db):
        from fichero_server.actions.registry import registry
        from fichero_server.models import SegmentPass

        page = self._converted_by_the_engine(db)
        [pass_row] = db.query(SegmentPass, document_id=page.id)
        registry.invoke(db, "pass.choose_working", {"document_id": page.id, "pass_id": pass_row.id},
                        self._person())
        assert page_text_is_derived(db, page.id) is True
