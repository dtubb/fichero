"""Named-entity extraction must bound its working set (#4379).

#4379's leading hypothesis for the dropped connection is memory: "NER over a
large document can pull a model or a large batch into memory, and this machine
sheds processes under pressure … NER needs to bound its working set
(batch/stream rather than load-everything) — and say so rather than dying."

Two separable contracts, tested separately so a regression names itself:

1. **Bounded concurrency.** No more than ``FICHERO_EXTRACT_MAX_IN_FLIGHT``
   extraction calls may be in flight at once. Deleting the semaphore turns a
   200-page document into 200 simultaneous model calls.
2. **Bounded input residency.** Document text must be read as extraction
   proceeds, not materialised for the whole selection before the first call.
   Reading everything up front makes peak memory scale with corpus size no
   matter how well concurrency is bounded — the exact shape that gets a
   process shed under pressure.

Contract 2 has no implementation today; the test asserting it FAILS, and that
failure is the finding (see its docstring).

Nothing here skips: these run entirely on stubs and a temp library, so an
absent model is not an excuse (#4365).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.integration._seedlib import seed

from fichero_server.db import Database, db_manager
from fichero_server.llm import LLMConfig
from fichero_server.models import DocType, Document, FileType
from fichero_server.workflows.runtime import build_initial_state

import fichero_server.workflows.tools  # noqa: F401
import fichero_server.workflows.tools.extract_all as extract_all_module
from fichero_server.workflows.tools.extract_entities_only import extract_entities_only

# Big enough that materialising every document at once is a real cost, small
# enough to stay a fast unit test.
_DOC_COUNT = 24
_DOC_TEXT = (
    "Regression Person signed the fixture deed in Regression Place in 1842. "
) * 40


def _no_entities():
    return extract_all_module._EntitiesOnly(
        people=[], places=[], organizations=[], dates=[], events=[]
    )


def _seed_many_documents(tmp_path: Path, name: str):
    library_path = tmp_path / f"{name}.fichero"
    seed(library_path)
    db = db_manager.get_database(library_path)

    folder = Document(id=f"{name}-folder", name=name, doc_type=DocType.folder)
    db.save(folder)
    doc_ids: list[str] = []
    for index in range(_DOC_COUNT):
        source_file = tmp_path / f"{name}-{index + 1}.txt"
        source_file.write_text(_DOC_TEXT, encoding="utf-8")
        doc = Document(
            id=f"{name}-doc-{index + 1}",
            parent_id=folder.id,
            name=source_file.name,
            path=str(source_file),
            doc_type=DocType.file,
            file_type=FileType.text,
            page_content=_DOC_TEXT,
            metadata={"transcription": _DOC_TEXT},
        )
        db.save(doc)
        doc_ids.append(doc.id)
    return library_path, folder.id, doc_ids


def _common_stubs(monkeypatch):
    monkeypatch.setattr(
        "fichero_server.llm.resolve_model_alias",
        lambda provider, model: ("fake", "fake-model"),
    )
    monkeypatch.setattr(Database, "embed", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "fichero_server.kg.entity_vectors.find_similar", lambda *a, **k: []
    )
    monkeypatch.setattr(
        "fichero_server.kg.entity_vectors.index_entity", lambda *a, **k: None
    )


def _run_tool(library_path: Path, folder_id: str, inputs: dict | None = None):
    state = build_initial_state(
        {"selected_doc_ids": [folder_id]}, library_path=str(library_path)
    )
    state["task_id"] = "bounded-working-set"
    return asyncio.run(
        extract_entities_only(
            inputs=inputs or {},
            state=state,
            llm_config=LLMConfig(provider="$small", model="$small"),
        )
    )


class TestBoundedConcurrency:
    def test_extraction_calls_never_exceed_the_in_flight_ceiling(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Peak simultaneous model calls must stay at or below the ceiling.

        Today ``extract_entities_only`` awaits each record inside its own
        ``async with extraction_sem`` in a plain ``for`` loop, so it is fully
        serial and observed peak is 1 — well inside the ceiling. That is
        fine; the point of this guard is the regression direction. Rewriting
        the loop as an ``asyncio.gather`` fan-out (an obvious "make NER
        faster" change) without keeping the semaphore in the awaited path
        makes peak jump to the selection size, and this test catches it.
        """
        ceiling = 3
        monkeypatch.setenv("FICHERO_EXTRACT_MAX_IN_FLIGHT", str(ceiling))
        _common_stubs(monkeypatch)

        in_flight = 0
        peak = 0

        async def slow_call(**_kwargs):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            try:
                # Yield control so any un-gated concurrency piles up here.
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                return _no_entities()
            finally:
                in_flight -= 1

        monkeypatch.setattr(
            "fichero_server.workflows.tools.extract_entities_only."
            "chat_structured_with_fallback",
            slow_call,
        )

        library_path, folder_id, doc_ids = _seed_many_documents(tmp_path, "ner-conc")
        result = _run_tool(library_path, folder_id)

        assert result["count"] == len(doc_ids), (
            f"expected all {len(doc_ids)} documents processed, got {result['count']}"
        )
        assert peak <= ceiling, (
            f"{peak} extraction calls were in flight at once with "
            f"FICHERO_EXTRACT_MAX_IN_FLIGHT={ceiling} — the working set is "
            "unbounded (#4379)"
        )
        assert peak > 0, "the stubbed model was never called"


class TestBoundedInputResidency:
    def test_document_text_is_read_as_extraction_proceeds_not_all_up_front(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Peak resident document text must not scale with the selection size.

        KNOWN FAILING against the current code (reported, not weakened).
        There is no bounded-working-set contract in the entity path today;
        this is the test asserting the contract that SHOULD hold.

        ``extract_entities_only`` calls ``_records_for_documents`` first,
        which walks EVERY selected document, pulls its full transcription
        (page_content, metadata, or the transcription artifact), and builds
        one list of records. Only then does it start extracting — one record
        at a time, under a semaphore. So concurrency is bounded but *input
        residency is not*: peak memory is the whole corpus's text, held for
        the entire run, regardless of how carefully the calls are paced.

        On the Marshall material (#4379: a real PDF run on a machine that
        sheds processes under memory pressure) that is the difference between
        a run that survives its own duration and a process the OS kills
        mid-extraction — which the client sees as "Lost connection to the
        Fichero server".

        The contract asserted: by the time the FIRST extraction call is made,
        at most a bounded prefix of the selection has been read. A streaming
        or page-at-a-time implementation satisfies it; load-everything does
        not.
        """
        ceiling = 3
        monkeypatch.setenv("FICHERO_EXTRACT_MAX_IN_FLIGHT", str(ceiling))
        _common_stubs(monkeypatch)

        import fichero_server.workflows.tools.extract_entities_only as module

        real_transcription_text = module._transcription_text
        texts_read = 0
        texts_read_at_first_call: int | None = None

        def counting_transcription_text(document, db):
            nonlocal texts_read
            texts_read += 1
            return real_transcription_text(document, db)

        async def observing_call(**_kwargs):
            nonlocal texts_read_at_first_call
            if texts_read_at_first_call is None:
                texts_read_at_first_call = texts_read
            return _no_entities()

        monkeypatch.setattr(module, "_transcription_text", counting_transcription_text)
        monkeypatch.setattr(module, "chat_structured_with_fallback", observing_call)

        library_path, folder_id, doc_ids = _seed_many_documents(tmp_path, "ner-resident")
        result = _run_tool(library_path, folder_id)

        assert result["count"] == len(doc_ids), (
            f"expected all {len(doc_ids)} documents processed, got {result['count']}"
        )
        assert texts_read_at_first_call is not None, (
            "the stubbed model was never called — nothing was extracted"
        )

        # A streaming implementation has read at most the documents it needs
        # to keep the in-flight ceiling busy, plus one lookahead.
        allowed = ceiling + 1
        assert texts_read_at_first_call <= allowed, (
            f"{texts_read_at_first_call} of {len(doc_ids)} documents had their "
            f"full text loaded before the first extraction call (bound: "
            f"{allowed}). Entity extraction materialises the entire selection "
            "up front, so peak memory scales with corpus size (#4379)."
        )
