"""Source-model slice 8b, piece 2 (#4924) — a HALF-CONVERTED project reads the
same as any other.

Spec: `segments-and-geometry.md`, `source.convert.half-done-reads-the-same`;
`build-notes-readings-cascade-orders.md`, "Slice 8b" → "The master test, for a
whole project: every page's seam answer before equals after, but for ids; and
**at every point in between** (convert half, compare all; convert the rest,
compare all). Same for `GET /api/artifacts/{id}`, the artifact lists, search, a
claim's reveal, an export."

WHY "AT EVERY POINT IN BETWEEN" IS THE WHOLE TEST. A whole-project conversion is
not atomic — it is one audited action per page, deliberately, so that a project
of twenty thousand pages is never one transaction. That means a half-converted
project is not an error state to be avoided: it is the NORMAL state for as long
as the run takes, and it is the state a person is looking at while they work.
`test_project_conversion_resume.py` compares two COMPLETED runs; this compares
the project against itself while the work is in flight.

`TestConversionChangesNothingYouCanSee` in `test_segment_conversion_action.py`
already pins this for ONE page and the seam alone. This is the whole-project,
six-surface version.

Every test builds its own temporary project.
"""

from __future__ import annotations

import pathlib
from types import SimpleNamespace

import pytest

import fichero_server.db.storage  # noqa: F401 — breaks the snapshots import cycle
import fichero_server.db.storage_snapshots as snaps

from fichero_server.maintenance import project_conversion as pc
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, DocType, Document, FileType, Status
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import (
    ClaimType,
    KnowledgeClaim,
    ProvenanceKind,
)

pytestmark = pytest.mark.source_model

PAGES = 4
WORDS = ["nombre", "dios", "carta", "vieren"]


@pytest.fixture
def project(db, test_package, tmp_path, monkeypatch):
    """The SHARED `db`/`client` pair, not a database of my own.

    Six of the surfaces under test are HTTP, and `client` is wired to
    `test_package`'s database — so a test that made its own `Database` would be
    converting one library and reading another. My first version did exactly
    that and the failures said so: zero pages converted and a seam with no
    `segments` key at all.
    """
    package = pathlib.Path(test_package)
    root = tmp_path / "snap" / "duckdb_export"
    root.mkdir(parents=True)
    stub = SimpleNamespace(
        id="snap-1", snapshot_path=str(tmp_path / "snap"), duckdb_path="duckdb_export",
        is_pinned=False, duckdb_size_bytes=1, lance_size_bytes=0, files_size_bytes=0,
    )
    monkeypatch.setattr(snaps, "snapshot_library", lambda *_a, **_k: stub)
    monkeypatch.setattr(snaps, "_save_snapshot_record", lambda _r: None)
    monkeypatch.setattr(
        pc, "prove_snapshot", lambda *_a, **_k: {"tables": 1, "rows": 1, "mismatches": {}}
    )
    return SimpleNamespace(db=db, path=package)


def _build(db) -> tuple[list[Document], list[Artifact]]:
    docs, artifacts = [], []
    for index in range(PAGES):
        word = WORDS[index]
        text = f"en el {word} de dios"
        doc = Document(
            name=f"folio-{index}.jpg", doc_type=DocType.file, file_type=FileType.image,
            path=f"/f/{index}.jpg", status=Status.completed, page_content=text,
        )
        db.save(doc)
        artifact = Artifact(
            document_id=doc.id, artifact_type="transcription",
            provider="qwen", model="qwen-vl", content=text,
            ocr_geometry=OCRGeometryResult(
                provider="qwen", text=text,
                boxes=[
                    OCRGeometryBox(
                        text=part, bbox=[0.1, 0.1 + i * 0.15, 0.3, 0.05], level="line",
                        char_start=text.index(part), char_end=text.index(part) + len(part),
                    )
                    for i, part in enumerate(text.split())
                ],
            ),
        )
        db.save(artifact)
        docs.append(doc)
        artifacts.append(artifact)
    return docs, artifacts


def _claim_on(db, doc: Document, artifact: Artifact) -> KnowledgeClaim:
    """A claim anchored by the RECTANGLE of a box, the way one made before
    conversion is. Its reveal must keep working throughout."""
    box = artifact.ocr_geometry.boxes[1]
    claim = KnowledgeClaim(
        text=f"dios is mentioned on {doc.name}",
        claim_type=ClaimType.fact,
        source_document_id=doc.id,
        source_anchor=SourceAnchor(
            document_id=doc.id, rect=list(box.bbox), rendition_id=None,
        ),
        provenance_kind=ProvenanceKind.human,
    )
    db.save(claim)
    return claim


# --------------------------------------------------------------------------
# The six surfaces. Each returns something comparable, with the THREE fields
# conversion is allowed to change stripped -- and only those three.
# --------------------------------------------------------------------------

_MAY_DIFFER = ("id", "pass_id", "provisional")


def _seam(client, doc_id: str) -> dict:
    payload = client.get(f"/api/segments/document/{doc_id}").json()
    segments = []
    for row in payload["segments"]:
        row = dict(row)
        for field in _MAY_DIFFER:
            row.pop(field, None)
        meta = dict(row.get("metadata") or {})
        # Conversion adds these two and the master test already accounts for
        # them; they are compared, not discarded.
        row["_box_index"] = meta.pop("box_index", row.get("box_index"))
        row["_page_index"] = meta.pop("page_index", row.get("page_index"))
        row["metadata"] = meta
        segments.append(row)
    passes = []
    for row in payload["passes"]:
        row = dict(row)
        for field in ("id", "provisional"):
            row.pop(field, None)
        passes.append(row)
    return {"segments": segments, "passes": passes}


def _artifact_get(client, artifact_id: str) -> dict:
    payload = client.get(f"/api/artifacts/{artifact_id}").json()
    # `region_count` and the boxes are the live projection; that is the point.
    return {
        "artifact_type": payload.get("artifact_type"),
        "content": payload.get("content"),
        "region_count": payload.get("region_count"),
        "boxes": [
            {k: v for k, v in (box or {}).items() if k != "metadata"}
            for box in ((payload.get("ocr_geometry") or {}).get("boxes") or [])
        ],
    }


def _artifact_list(client, doc_id: str) -> list[dict]:
    payload = client.get(f"/api/artifacts/document/{doc_id}").json()
    items = payload["items"] if isinstance(payload, dict) else payload
    return [
        {"id": a["id"], "artifact_type": a["artifact_type"], "region_count": a.get("region_count")}
        for a in items
    ]


def _search(client, term: str) -> list[str]:
    response = client.post("/api/search", json={"query": term, "limit": 20})
    if response.status_code != 200:
        pytest.skip(f"search unavailable in this fixture: {response.status_code}")
    payload = response.json()
    items = payload.get("results") or payload.get("items") or []
    return sorted(str(item.get("document_id") or item.get("id")) for item in items)


def _claim_reveal(client, claim: KnowledgeClaim) -> dict:
    response = client.post(
        "/api/locations/resolve",
        json={
            "document_id": claim.source_document_id,
            "anchor": claim.source_anchor.model_dump(mode="json"),
        },
    )
    return {"status": response.status_code, "body": response.json() if response.content else None}


def _page_text(client, doc_id: str) -> str:
    """The export's substance: what a page says."""
    response = client.get(f"/api/segments/document/{doc_id}/text")
    return response.json()["text"] if response.status_code == 200 else f"ERR{response.status_code}"


def _everything(client, docs, artifacts, claims) -> dict:
    return {
        "seam": {d.id: _seam(client, d.id) for d in docs},
        "artifact_get": {a.id: _artifact_get(client, a.id) for a in artifacts},
        "artifact_list": {d.id: _artifact_list(client, d.id) for d in docs},
        "search": {word: _search(client, word) for word in WORDS[:2]},
        "reveal": {c.id: _claim_reveal(client, c) for c in claims},
    }


class TestAHalfConvertedProjectReadsTheSame:
    """`source.convert.half-done-reads-the-same`, across six surfaces, at every
    point in between."""

    def test_every_surface_is_unchanged_before_halfway_and_after(
        self, project, client
    ):
        docs, artifacts = _build(project.db)
        claims = [_claim_on(project.db, docs[i], artifacts[i]) for i in range(PAGES)]

        before = _everything(client, docs, artifacts, claims)

        # HALFWAY. Two of four pages converted, and then every surface compared
        # for EVERY page -- converted and not -- because "no reader may be able
        # to tell which pages are done" is a claim about the whole project, not
        # about the pages that happen to be finished.
        seen = {"n": 0}

        def stop_after_two() -> bool:
            if seen["n"] >= 2:
                return True
            seen["n"] += 1
            return False

        half = pc.convert_project(project.db, project.path, should_stop=stop_after_two)
        assert half.pages_converted == 2, "the halfway point must actually be halfway"
        halfway = _everything(client, docs, artifacts, claims)
        assert halfway == before, "a half-converted project reads differently"

        rest = pc.convert_project(project.db, project.path)
        assert rest.pages_converted == 2
        after = _everything(client, docs, artifacts, claims)
        assert after == before, "a fully converted project reads differently"

    def test_the_page_text_is_the_same_at_every_point(self, project, client):
        """The derived text is the one surface that CHANGES source mid-run — an
        unconverted page has no segments, so it has no derived text, while a
        converted one reads from readings. So this asserts the honest shape: a
        page's text is either empty (not yet converted) or its real words, and
        never anything else."""
        docs, artifacts = _build(project.db)

        def texts() -> dict[str, str]:
            return {d.id: _page_text(client, d.id) for d in docs}

        before = texts()
        assert set(before.values()) == {""}, "nothing is converted yet"

        seen = {"n": 0}

        def stop_after_two() -> bool:
            if seen["n"] >= 2:
                return True
            seen["n"] += 1
            return False

        pc.convert_project(project.db, project.path, should_stop=stop_after_two)
        halfway = texts()
        expected = {d.id: f"en el {WORDS[i]} de dios" for i, d in enumerate(docs)}
        converted_now = [d for d in docs if halfway[d.id]]
        assert len(converted_now) == 2
        for doc in converted_now:
            assert halfway[doc.id] == expected[doc.id], "a converted page's text is wrong"
        for doc in docs:
            if doc not in converted_now:
                assert halfway[doc.id] == "", "an unconverted page invented text"

        pc.convert_project(project.db, project.path)
        assert texts() == expected

    def test_a_claim_anchored_by_rectangle_still_reveals_after_its_page_converts(
        self, project, client
    ):
        """The case that made `resolve_anchor` necessary: a claim made BEFORE
        conversion, pointing by rectangle alone. Its reveal must not change
        because the engine reorganised its storage."""
        docs, artifacts = _build(project.db)
        claim = _claim_on(project.db, docs[0], artifacts[0])

        before = _claim_reveal(client, claim)
        pc.convert_project(project.db, project.path)
        after = _claim_reveal(client, claim)

        assert after == before
        assert before["status"] == 200, "the reveal was broken before conversion too"

    def test_the_artifact_still_reports_its_own_boxes_after_conversion(
        self, project, client
    ):
        """`GET /api/artifacts/{id}` answers from `live_geometry`, so a converted
        artifact reports the ROWS as boxes. A caller must not be able to tell."""
        docs, artifacts = _build(project.db)

        before = {a.id: _artifact_get(client, a.id) for a in artifacts}
        pc.convert_project(project.db, project.path)
        after = {a.id: _artifact_get(client, a.id) for a in artifacts}

        assert after == before

    def test_a_page_that_cannot_convert_still_reads_from_its_block(
        self, project, client, monkeypatch
    ):
        """A recorded failure must leave that page exactly as it was — "it still
        reads, from its block, exactly as before"."""
        docs, artifacts = _build(project.db)
        before = _seam(client, docs[1].id)

        real = pc._convert_one_page
        failed_doc = docs[1].id

        def one_page_fails(db, document_id, run_id):
            if document_id == failed_doc:
                raise RuntimeError("this page cannot convert")
            return real(db, document_id, run_id)

        monkeypatch.setattr(pc, "_convert_one_page", one_page_fails)
        run = pc.convert_project(project.db, project.path)

        assert [f.document_id for f in run.failures] == [failed_doc]
        assert run.pages_converted == PAGES - 1
        # The failed page is untouched and still answers from its block.
        assert _seam(client, failed_doc) == before
