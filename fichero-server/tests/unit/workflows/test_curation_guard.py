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
