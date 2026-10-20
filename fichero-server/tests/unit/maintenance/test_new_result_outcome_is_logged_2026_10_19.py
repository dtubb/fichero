"""'Text but no boxes' (owner, 2026-10-19) could not be answered from the engine log: a page's new result became a pass,
was skipped or failed, and only a failure was logged (`source.convert.a-new-result-is-a-pass-at-once`). Every outcome is
now one line naming the page."""
from __future__ import annotations

import logging

import pytest

from fichero_server.maintenance import project_conversion


@pytest.mark.parametrize("outcome", ["converted", "skipped"])
def test_each_outcome_is_logged_with_the_page(monkeypatch, caplog, outcome):
    monkeypatch.setattr(project_conversion, "_convert_one_page", lambda db, document_id, run_id: outcome)
    with caplog.at_level(logging.INFO, logger=project_conversion.logger.name):
        assert project_conversion.convert_new_results(object(), "page-7") == outcome
    assert f"A new result on page page-7: {outcome}" in caplog.text


def test_a_failure_is_still_logged_as_an_error_and_returns_failed(monkeypatch, caplog):
    def boom(db, document_id, run_id):
        raise RuntimeError("no room")

    monkeypatch.setattr(project_conversion, "_convert_one_page", boom)
    assert project_conversion.convert_new_results(object(), "page-8") == "failed"
    assert "page-8 did not become a pass" in caplog.text and "no room" in caplog.text
