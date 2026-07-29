#!/usr/bin/env python
"""Build a deterministic ``.fichero`` test library for integration testing.

The same seeded library anchors both ends of the app<->engine contract:
- the Python contract walker (tests/integration/test_contract_endpoint_walk.py),
- the Swift round-trip integration tests (drive the live engine, assert the
  app decodes the same data the engine holds).

Why a builder script and not a committed ``.fichero`` binary: a library is a
DuckDB file, and under the 0.0.x no-migration rule the schema evolves with the
models. A checked-in binary would rot; regenerating from the current models
every run keeps the fixture in lock-step with the code.

Usage:
    PYTHONPATH=fichero-server/src python fichero-server/scripts/seed_test_library.py <path> [--with-files]

``--with-files`` additionally copies real specimens from the shared
``test-fixtures/files`` tree into the library and registers file-backed
documents plus two extra canonical workflows. The default (no flag) output is
byte-for-byte the historical seed, so existing consumers are unaffected.

Prints a JSON summary (counts + key IDs) to stdout so a harness/CI can verify.
IDs are fixed so tests can assert on specific values.
"""

from __future__ import annotations

import json
import shutil
import sys
import base64
from pathlib import Path

from fichero_server.db import db_manager
from fichero_server.models import Artifact, Document, DocType, FileType, Status, Workflow
from fichero_server.models.knowledge import (
    ClaimType,
    EpistemicStatus,
    KnowledgeClaim,
    KnowledgeEntity,
)

# Fixed IDs — tests assert against these exact values.
COLLECTION_ID = "test-collection"
DOC_LETTER_ID = "test-doc-letter"
DOC_PHOTO_ID = "test-doc-photo"
PAGE_ID = "test-page-1"
ENTITY_PERSON_ID = "test-ent-person"
ENTITY_PLACE_ID = "test-ent-place"
ENTITY_ORG_ID = "test-ent-org"
CLAIM_IDS = ["test-claim-1", "test-claim-2", "test-claim-3"]
WORKFLOW_ID = "test-workflow-catalogue"
ARTIFACT_ID = "test-artifact-transcription"
# --with-files additions — real specimens from the shared fixture library.
SAMPLE_FILES_DIR = Path(__file__).resolve().parents[2] / "test-fixtures" / "files"
FIXTURE_DOC_SPECS = [
    ("test-doc-fixture-pdf", "multipage.pdf", FileType.pdf),
    ("test-doc-fixture-jpg", "sample.jpg", FileType.image),
    ("test-doc-fixture-txt", "sample.txt", FileType.text),
]
EXTRA_WORKFLOW_IDS = ["test-workflow-transcribe", "test-workflow-entities"]
_ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j5tQAAAAASUVORK5CYII="
)

def _measure(db) -> dict:
    """Ground-truth counts read back from the library after seeding.

    Derived from the data, never hand-declared — so "expected" can't drift from
    what was actually seeded. The integration test compares the engine's
    over-HTTP counts against these, proving the API/envelope layer exposes
    exactly what the library holds (no rows dropped by pagination defaults,
    envelope wrapping, or scoping).
    """
    return {
        "documents_total": len(db.all(Document)),
        "collections": len(db.query(Document, parent_id=None)),
        "children_of_collection": len(db.query(Document, parent_id=COLLECTION_ID)),
        "entities": len(db.all(KnowledgeEntity)),
        "claims": len(db.all(KnowledgeClaim)),
        "workflows": len(db.all(Workflow)),
        "artifacts_for_letter": len(db.query(Artifact, document_id=DOC_LETTER_ID)),
    }


def _make_package(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    (path / "lance").mkdir()
    (path / "storage").mkdir()
    (path / "files").mkdir()


def _seed_fixture_files(db, path: Path) -> None:
    """Copy real shared specimens into the library as file-backed documents."""
    for doc_id, fixture_name, file_type in FIXTURE_DOC_SPECS:
        src = SAMPLE_FILES_DIR / fixture_name
        if not src.is_file():
            raise FileNotFoundError(f"shared fixture missing: {src}")
        dst = path / "files" / f"{doc_id}{src.suffix}"
        shutil.copyfile(src, dst)
        db.save(
            Document(
                id=doc_id,
                parent_id=COLLECTION_ID,
                name=fixture_name,
                doc_type=DocType.file,
                file_type=file_type,
                status=Status.completed,
                path=str(dst.relative_to(path)),
            )
        )
    for wf_id, wf_name in zip(
        EXTRA_WORKFLOW_IDS, ["Test Transcribe", "Test Extract Entities"]
    ):
        db.save(
            Workflow(
                id=wf_id,
                name=wf_name,
                description="Seeded canonical workflow for cross-layer tests.",
                folder_path="/",
            )
        )


def seed(path: Path, with_files: bool = False) -> dict:
    _make_package(path)
    photo_path = path / "files" / "test-doc-photo.png"
    photo_path.write_bytes(_ONE_PIXEL_PNG)
    db = db_manager.get_database(path)

    # --- document hierarchy: collection > files > page ---------------------
    db.save(Document(id=COLLECTION_ID, name="Test Archive", doc_type=DocType.folder))
    db.save(
        Document(
            id=DOC_LETTER_ID,
            parent_id=COLLECTION_ID,
            name="Letter 1933",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            status=Status.completed,
            page_content="A letter from Eugenio to the Ministry in Bogotá.",
        )
    )
    db.save(
        Document(
            id=DOC_PHOTO_ID,
            parent_id=COLLECTION_ID,
            name="Photo 1965",
            doc_type=DocType.file,
            file_type=FileType.image,
            status=Status.completed,
            path=str(photo_path.relative_to(path)),
        )
    )
    db.save(
        Document(
            id=PAGE_ID,
            parent_id=DOC_LETTER_ID,
            name="Letter 1933 — p1",
            doc_type=DocType.page,
            sequence=1,
            page_content="Page one body text.",
        )
    )

    # --- knowledge graph: entities + claims --------------------------------
    db.save(KnowledgeEntity(id=ENTITY_PERSON_ID, canonical_name="Eugenio Córdoba"))
    db.save(KnowledgeEntity(id=ENTITY_PLACE_ID, canonical_name="Bogotá"))
    db.save(KnowledgeEntity(id=ENTITY_ORG_ID, canonical_name="Ministry of Education"))

    claim_specs = [
        (CLAIM_IDS[0], DOC_LETTER_ID, [ENTITY_PERSON_ID, ENTITY_PLACE_ID]),
        (CLAIM_IDS[1], DOC_LETTER_ID, [ENTITY_PERSON_ID, ENTITY_ORG_ID]),
        (CLAIM_IDS[2], DOC_PHOTO_ID, [ENTITY_PLACE_ID]),
    ]
    for cid, doc_id, entity_ids in claim_specs:
        db.save(
            KnowledgeClaim(
                id=cid,
                text=f"Seeded claim {cid}",
                source_document_id=doc_id,
                source_ids=[doc_id],
                claim_type=ClaimType.fact,
                epistemic_status=EpistemicStatus.tentative,
                confidence=0.8,
                entity_ids=entity_ids,
            )
        )

    # --- a workflow --------------------------------------------------------
    db.save(
        Workflow(
            id=WORKFLOW_ID,
            name="Test Catalogue",
            description="Seeded workflow for integration tests.",
            folder_path="/",
        )
    )

    # --- an artifact on the letter -----------------------------------------
    db.save(
        Artifact(
            id=ARTIFACT_ID,
            document_id=DOC_LETTER_ID,
            artifact_type="transcription",
            content="A letter from Eugenio to the Ministry in Bogotá.",
        )
    )

    if with_files:
        _seed_fixture_files(db, path)

    expected = _measure(db)
    db_manager.close_all()
    return {
        "path": str(path),
        "expected": expected,
        # Flat name->id map so consumers (the Swift integration harness, the
        # Python walker) reference seeded rows by name, never by a hardcoded id.
        "keys": {
            "collection": COLLECTION_ID,
            "doc_letter": DOC_LETTER_ID,
            "doc_photo": DOC_PHOTO_ID,
            "page": PAGE_ID,
            "entity_person": ENTITY_PERSON_ID,
            "workflow": WORKFLOW_ID,
            "artifact": ARTIFACT_ID,
        },
        "ids": {
            "collection": COLLECTION_ID,
            "documents": [COLLECTION_ID, DOC_LETTER_ID, DOC_PHOTO_ID, PAGE_ID],
            "entities": [ENTITY_PERSON_ID, ENTITY_PLACE_ID, ENTITY_ORG_ID],
            "claims": CLAIM_IDS,
            "workflow": WORKFLOW_ID,
            "artifact": ARTIFACT_ID,
        },
    }


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--with-files"]
    with_files = "--with-files" in sys.argv[1:]
    if len(args) < 1:
        print(
            "usage: seed_test_library.py <path-to.fichero> [--with-files]",
            file=sys.stderr,
        )
        return 2
    target = Path(args[0]).expanduser().resolve()
    if target.suffix != ".fichero":
        print(f"refusing to seed non-.fichero path: {target}", file=sys.stderr)
        return 2
    summary = seed(target, with_files=with_files)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
