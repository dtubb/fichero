"""An import must be able to say how many documents it embedded (#4395, #4302).

Phase 1 measured Daniel's real libraries: Local holds 668 documents with text
and 0 embeddings; Marshall holds 452 and 449. Nobody noticed for weeks,
because no import has ever reported an embedding count. The question "are
embeddings working?" required copying a DuckDB file and reading a Lance
table. The app should be able to answer it.

Two contracts, tested separately so a regression names itself.

**A. PDF page children must be embedded, or the caller must be told they
were not.** `_create_pdf_page_children` declares ``auto_embed: bool = False``
(``importers/ingest.py:502``), and the two workflow call sites pass ``False``
explicitly:

    workflows/tools/sources.py:364      files_tool on-the-spot PDF split
    workflows/tools/vision_base.py:2583 whole-PDF guard split

while ingest (``:399``) and the backfill route
(``api/routes/document/documents.py:1492``) pass ``True``. Selecting a PDF in
a workflow therefore produces page children that carry the document's entire
text and are never embedded by anything, ever. That is the measured cause of
Local's 668-to-0: 666 of those documents are exactly these page children,
with ≥200 characters each, well above ``MIN_CONTENT_LENGTH``.

Whether the default should flip is a product call. What is not a product call
is that the decision is currently invisible: nothing records that a split
produced N unembedded pages, so no later pass can find them and no user can
be told.

**B. A run that embeds nothing is a broken run.** Same rule as #4283 — a run
that produced nothing must not report success. That guard was proven
structurally unreachable for all sixteen workflow families; the import path
does not have one at all.

Both tests FAIL today. No test skips (#4365).
"""

from __future__ import annotations

import inspect
import shutil
import tempfile
from pathlib import Path

import pytest

from fichero_server.importers import ingest as ingest_module


@pytest.fixture
def temp_library():
    tmpdir = tempfile.mkdtemp()
    yield Path(tmpdir)
    shutil.rmtree(tmpdir, ignore_errors=True)


class TestPageChildrenEmbeddingIsNotSilentlySkipped:
    def test_page_children_default_to_being_embedded(self):
        """The default decides the outcome for callers that don't opt in.

        KNOWN FAILING — the default is ``False``.

        A default of ``False`` on a private helper means every new call site
        silently inherits "do not embed", and the two workflow call sites
        already have. Defaults should fail safe: the safe direction here is
        that a page carrying a document's text is searchable.
        """
        signature = inspect.signature(ingest_module._create_pdf_page_children)
        default = signature.parameters["auto_embed"].default

        assert default is True, (
            "_create_pdf_page_children defaults to auto_embed=False, so any "
            "call site that does not explicitly opt in produces page children "
            "that carry the document's text and are never embedded. Two "
            "workflow call sites (sources.py, vision_base.py) already pass "
            "False, which measurably left 666 documents unsearchable in "
            "Daniel's Local library (#4395)."
        )

    def test_every_page_children_call_site_makes_an_explicit_choice(self):
        """If not embedding is deliberate, it must be recorded, not implied.

        Reading the call sites rather than the message text: every caller of
        ``_create_pdf_page_children`` must pass ``auto_embed`` explicitly, so
        the decision is visible at the point it is made and greppable
        afterwards. A caller that omits it has made no decision at all — it
        has inherited one.
        """
        import fichero_server.workflows.tools.sources as sources_module
        import fichero_server.workflows.tools.vision_base as vision_module
        import fichero_server.api.routes.document.documents as documents_module

        callers = {
            "importers/ingest.py": ingest_module,
            "workflows/tools/sources.py": sources_module,
            "workflows/tools/vision_base.py": vision_module,
            "api/routes/document/documents.py": documents_module,
        }
        missing: list[str] = []
        for label, module in callers.items():
            source = inspect.getsource(module)
            if "_create_pdf_page_children(" not in source:
                missing.append(f"{label}: call site vanished — update this test")
                continue
            for chunk in source.split("_create_pdf_page_children(")[1:]:
                head = chunk[:200]
                if "auto_embed" not in head:
                    missing.append(f"{label}: a call omits auto_embed")

        assert missing == [], (
            "these call sites do not state their embedding intent: "
            f"{missing}. An implicit choice cannot be reviewed or found later."
        )


class TestImportReportsEmbeddingCounts:
    def test_ingest_reports_how_many_documents_were_embedded(self):
        """An import must be able to answer 'are embeddings working?'.

        KNOWN FAILING — no such report exists.

        ``ingest_file`` returns Documents; ``db.embed()``'s return value is
        discarded at both call sites (``ingest.py:392``, ``ingest.py:640``).
        Nothing counts successes, nothing counts skips, nothing counts
        failures, and nothing records a reason. That is why answering this
        question for three libraries required reading their databases
        directly.

        The contract: the import path must expose an embedding summary —
        embedded / skipped / failed with reasons — so the number is available
        without anyone reading code or copying a DuckDB file.
        """
        candidates = [
            name
            for name in dir(ingest_module)
            if "embed" in name.lower()
            and ("report" in name.lower() or "summary" in name.lower() or "stats" in name.lower())
        ]
        assert candidates, (
            "importers/ingest.py exposes no embedding report/summary/stats "
            "surface. An import that embeds 0 of 668 documents currently "
            "reports complete success, and the only way to discover otherwise "
            "is to query the vector store by hand (#4395)."
        )

    def test_embed_call_sites_do_not_discard_the_result(self):
        """A returned status nobody reads is the same as no status.

        Behavioural in the sense that matters: this asserts on the call
        structure in the AST, not on any message text. ``db.embed(doc)`` as a
        bare expression statement discards the outcome; a real handler
        assigns it, tests it, or accumulates it.
        """
        import ast

        source = inspect.getsource(ingest_module)
        tree = ast.parse(source)
        discarded: list[int] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
                continue
            func = node.value.func
            if isinstance(func, ast.Attribute) and func.attr == "embed":
                discarded.append(node.lineno)

        assert discarded == [], (
            "db.embed(...) is called as a bare statement — its True/False "
            f"outcome is thrown away — at ingest.py source lines {discarded}. "
            "Whatever embed() reports, no import can act on it or count it."
        )
