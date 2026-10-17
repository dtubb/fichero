"""A names run that processes no page fails and says why (`source.job.names-step-fails-on-nothing-read`, #5521).

WHY: the M4 operator's spaCy names workflow and "NER per-page (local)" both ended "completed" over 0 pages with no
error, which reads as success when nothing was done.
"""
# ruff: noqa: F811  (the imported `library` fixture is used by name)
from __future__ import annotations

import asyncio

import pytest

from tests.unit.workflows.test_entities_read_the_working_pass import (  # noqa: F401
    _page,
    _run,
    library,
    module,
)


def test_a_names_run_over_pages_with_no_reading_fails_and_says_why_5521(library, tmp_path):
    path, db, folder, _seen = library
    _page(db, folder, tmp_path, "blank-a.jpg", imported=False)
    _page(db, folder, tmp_path, "blank-b.jpg", imported=False)

    result = _run(path, folder.id)

    assert "none of the 2 selected pages has a reading" in result["error"]
    assert "blank-a.jpg" in result["error"] and module.NO_TEXT[:20] in result["error"]
    assert result["summary"]["documents_processed"] == 0 and result["summary"]["documents_left_out"] == 2


def test_a_names_run_over_no_page_fails_and_says_so_5521(library):
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.runtime import build_initial_state

    path, _db, folder, _seen = library  # the folder holds no page
    state = build_initial_state({"selected_doc_ids": [folder.id]}, library_path=str(path))
    state["task_id"] = "names-no-page"
    with pytest.raises(ValueError, match="would process nothing"):  # the files source refuses it, loudly
        asyncio.run(module.extract_entities_only(
            inputs={}, state=state, llm_config=LLMConfig(provider="$small", model="$small")))


def test_a_page_left_out_beside_a_page_read_still_completes_5521(library, tmp_path):
    path, db, folder, _seen = library
    _page(db, folder, tmp_path, "0074.jpg", imported=True)
    _page(db, folder, tmp_path, "blank.jpg", imported=False)

    result = _run(path, folder.id)

    assert not result.get("error") and result["summary"]["documents_left_out"] == 1
