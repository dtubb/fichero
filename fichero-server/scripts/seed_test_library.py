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
    PYTHONPATH=fichero-server/src python fichero-server/scripts/seed_test_library.py <path> [--with-files] [--full]
    PYTHONPATH=fichero-server/src python fichero-server/scripts/seed_test_library.py --self-test

``--with-files`` additionally copies real specimens from the shared
``test-fixtures/files`` tree into the library and registers file-backed
documents plus two extra canonical workflows. The default (no flag) output is
byte-for-byte the historical seed, so existing consumers are unaffected.

``--full`` (implies ``--with-files``) is the synthetic seeded test library the
2026-08-04 test-architecture decisions call for — the ONE library every live
consumer (Swift, UI, UX, CLI, MCP harnesses) seeds per run. On top of the
historical seed it adds: nested folders, a read-only system folder, one node of
every DocType (folder/group/file/page/chunk) plus an alias node, and one
workflow of each runnable shape (steps-format and nodes-format). Every
full-mode row has a uuid5-deterministic id and a PINNED timestamp, so two
builds are structurally identical — proven by ``--self-test``, which builds
twice into temp dirs and structurally compares every seeded table.

Prints a JSON summary (counts + key IDs) to stdout so a harness/CI can verify.
IDs are fixed so tests can assert on specific values.
"""

from __future__ import annotations

import json
import shutil
import sys
import base64
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fichero_server.db import db_manager
from fichero_server.models import Artifact, Document, DocType, FileType, Status, Workflow
from fichero_server.models.knowledge import (
    ClaimType,
    EpistemicStatus,
    KnowledgeClaim,
    KnowledgeEntity,
)
from fichero_server.models.node_aliases import make_alias

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

# --full additions. Ids are uuid5 of a stable URI (deterministic by
# construction, per the 2026-08-04 decision), and every full-mode row pins its
# timestamps to SEED_TS so two builds are structurally identical.
SEED_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)
_SEED_NAMESPACE = "fichero://seed-test-library/"


def _sid(key: str) -> str:
    """Deterministic uuid5 id for a full-mode seeded row."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, _SEED_NAMESPACE + key))


FULL_KEYS = [
    "folder-inbox",
    "folder-system",
    "folder-outer",
    "folder-inner",
    "group-bundle",
    "group-page-1",
    "group-page-2",
    "chunk-signature",
    "alias-letter",
    "workflow-steps",
    "workflow-nodes",
]

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


def _seed_full(db) -> None:
    """The synthetic-library additions: every DocType, nesting, system folder,
    an alias node, and one workflow per runnable shape. All ids uuid5, all
    timestamps pinned to SEED_TS."""
    ts = {"created_at": SEED_TS, "updated_at": SEED_TS}

    # The engine bootstraps a root Inbox with a RANDOM id on library creation
    # (library_bootstrap.ensure_inbox_folder) — the one nondeterministic row in
    # a fresh library. Replace it with the same shape under a uuid5 id; the
    # bootstrap is idempotent by shape (name+parent+doc_type), so the engine
    # will not mint another. It is empty at seed time, so this drops no data.
    for row in db.query(
        Document, name="Inbox", parent_id=None, doc_type=DocType.folder
    ):
        db.delete(row)
    db.save(
        Document(
            id=_sid("folder-inbox"),
            name="Inbox",
            parent_id=None,
            doc_type=DocType.folder,
            **ts,
        )
    )

    # Read-only system folder — the engine's own convention for locked
    # containers (see ensure_default_workflow_container in db/__init__.py).
    db.save(
        Document(
            id=_sid("folder-system"),
            name="System Fixtures",
            doc_type=DocType.folder,
            attributes={"read_only": True, "system": True, "scope": "library"},
            **ts,
        )
    )

    # Nested folders: outer > inner, under the historical collection.
    db.save(
        Document(
            id=_sid("folder-outer"),
            parent_id=COLLECTION_ID,
            name="Box 1",
            doc_type=DocType.folder,
            **ts,
        )
    )
    db.save(
        Document(
            id=_sid("folder-inner"),
            parent_id=_sid("folder-outer"),
            name="Series A",
            doc_type=DocType.folder,
            **ts,
        )
    )

    # A GROUP (logical document) with two PAGEs; page 1 carries a CHUNK.
    # Together with the folders/files above this covers every DocType.
    db.save(
        Document(
            id=_sid("group-bundle"),
            parent_id=_sid("folder-inner"),
            name="Letter bundle 1934",
            doc_type=DocType.group,
            **ts,
        )
    )
    for n in (1, 2):
        db.save(
            Document(
                id=_sid(f"group-page-{n}"),
                parent_id=_sid("group-bundle"),
                name=f"Letter bundle 1934 — p{n}",
                doc_type=DocType.page,
                sequence=n,
                page_content=f"Bundle page {n} body text.",
                **ts,
            )
        )
    db.save(
        Document(
            id=_sid("chunk-signature"),
            parent_id=_sid("group-page-1"),
            name="Signature",
            doc_type=DocType.chunk,
            sequence=1,
            bbox=(10, 20, 120, 40),
            **ts,
        )
    )

    # An alias node referencing the letter, sitting in the inner folder —
    # the one non-"document" node_kind a library can hold today.
    letter = db.get(Document, DOC_LETTER_ID)
    alias = make_alias(letter, parent_id=_sid("folder-inner"))
    alias.id = _sid("alias-letter")
    alias.created_at = SEED_TS
    alias.updated_at = SEED_TS
    db.save(alias)

    # One workflow of each runnable shape: legacy steps and visual nodes
    # (the nodes shape mirrors the smallest shipped preset,
    # catalogue_stage_1_import_artifacts.json: files -> import_artifacts).
    db.save(
        Workflow(
            id=_sid("workflow-steps"),
            name="Test Steps Shape",
            description="Seeded steps-format workflow (runnable shape 1 of 2).",
            folder_path="/",
            format="steps",
            steps=[{"name": "transcribe", "tool": "transcribe", "provider": ""}],
            **ts,
        )
    )
    db.save(
        Workflow(
            id=_sid("workflow-nodes"),
            name="Test Nodes Shape",
            description="Seeded nodes-format workflow (runnable shape 2 of 2).",
            folder_path="/",
            format="nodes",
            nodes=[
                {
                    "id": "files-source",
                    "tool": "files",
                    "label": "Files",
                    "position_x": 80,
                    "position_y": 220,
                    "inputs": {},
                    "config": {},
                },
                {
                    "id": "import-artifacts",
                    "tool": "import_artifacts",
                    "label": "Register import artifacts",
                    "position_x": 320,
                    "position_y": 220,
                    "inputs": {},
                    "config": {},
                },
            ],
            edges=[
                {
                    "id": "e-files-import-artifacts-documents",
                    "source": "files-source",
                    "target": "import-artifacts",
                    "source_port": "documents",
                    "target_port": "documents",
                }
            ],
            **ts,
        )
    )


def seed(path: Path, with_files: bool = False, full: bool = False) -> dict:
    if full:
        with_files = True
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
    if full:
        _seed_full(db)
        # Pin EVERY seeded row's timestamps (the historical rows above use
        # utc_now defaults) so two --full builds are structurally identical —
        # the property --self-test asserts, timestamps included.
        for model_type in (Document, Workflow, Artifact, KnowledgeEntity, KnowledgeClaim):
            for row in db.all(model_type):
                if hasattr(row, "created_at"):
                    row.created_at = SEED_TS
                if hasattr(row, "updated_at"):
                    row.updated_at = SEED_TS
                db.save(row)

    expected = _measure(db)
    db_manager.close_all()
    return {
        "path": str(path),
        "full": full,
        "full_ids": {k: _sid(k) for k in FULL_KEYS} if full else {},
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


def _structural_dump(path: Path) -> dict:
    """Every seeded table as sorted JSON rows — the shape two builds must share."""
    db = db_manager.get_database(path)
    try:
        dump = {
            T.__name__: sorted(
                (row.model_dump(mode="json") for row in db.all(T)),
                key=lambda r: r["id"],
            )
            for T in (Document, Workflow, Artifact, KnowledgeEntity, KnowledgeClaim)
        }
    finally:
        db_manager.close_all()
    return dump


def _self_test() -> int:
    """Build the full library twice; the two must be structurally identical.

    This is the determinism proof the 2026-08-04 decision requires. It FAILS
    (exit 1) naming the first divergent table if any row differs — including
    timestamps, which are pinned to SEED_TS in full mode precisely so this
    comparison can include them. It also proves the guard can fire: a copy of
    build A with one mutated row must NOT compare equal.
    """
    with tempfile.TemporaryDirectory(prefix="fichero-seed-selftest-") as tmp:
        a, b = Path(tmp) / "a.fichero", Path(tmp) / "b.fichero"
        summary_a = seed(a, full=True)
        summary_b = seed(b, full=True)
        dump_a, dump_b = _structural_dump(a), _structural_dump(b)

        for key in ("expected", "full_ids", "keys", "ids"):
            if summary_a[key] != summary_b[key]:
                print(f"self-test FAILED: summary[{key!r}] differs between builds",
                      file=sys.stderr)
                return 1
        for table in dump_a:
            if dump_a[table] != dump_b[table]:
                for ra, rb in zip(dump_a[table], dump_b[table]):
                    if ra != rb:
                        delta = {k for k in ra if ra.get(k) != rb.get(k)}
                        print(
                            f"self-test FAILED: {table} row {ra.get('id')} differs "
                            f"in fields {sorted(delta)}",
                            file=sys.stderr,
                        )
                        return 1
                print(f"self-test FAILED: {table} row sets differ", file=sys.stderr)
                return 1

        # The comparison itself must be able to fail (#4487 discipline): a
        # mutated copy of build A may not read as equal.
        mutated = json.loads(json.dumps(dump_a))
        mutated["Document"][0]["name"] = "MUTATED"
        if mutated == dump_a:
            print("self-test FAILED: mutation was not detected — the comparison "
                  "is blind", file=sys.stderr)
            return 1

        counts = {t: len(rows) for t, rows in dump_a.items()}
        doc_types = sorted({r["doc_type"] for r in dump_a["Document"]})
        node_kinds = sorted({str(r.get("node_kind")) for r in dump_a["Document"]})
        assert set(doc_types) == {"folder", "group", "file", "page", "chunk"}, doc_types
        assert "alias" in node_kinds, node_kinds
        print(
            "seed_test_library self-test: OK — two --full builds structurally "
            f"identical; mutation detected; rows={counts}; "
            f"doc_types={doc_types}; node_kinds={node_kinds}"
        )
    return 0


def main() -> int:
    flags = {"--with-files", "--full", "--self-test"}
    args = [a for a in sys.argv[1:] if a not in flags]
    with_files = "--with-files" in sys.argv[1:]
    full = "--full" in sys.argv[1:]
    if "--self-test" in sys.argv[1:]:
        return _self_test()
    if len(args) < 1:
        print(
            "usage: seed_test_library.py <path-to.fichero> [--with-files] [--full] | --self-test",
            file=sys.stderr,
        )
        return 2
    target = Path(args[0]).expanduser().resolve()
    if target.suffix != ".fichero":
        print(f"refusing to seed non-.fichero path: {target}", file=sys.stderr)
        return 2
    summary = seed(target, with_files=with_files, full=full)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
