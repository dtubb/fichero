"""Perf benchmark for the entity-list hot path (#1815).

NOT part of the default unit gate — lives under tests/perf/ so
`pytest tests/unit/` skips it. Run explicitly:

    PYTHONPATH=fichero-server/src .venv/bin/pytest fichero-server/tests/perf/ -q -s

Why this endpoint: ``list_entities`` does ``db.all(KnowledgeEntity)`` and, in
the ``document_id`` branch, a full ``db.query(KnowledgeClaim)`` scan plus a
second ``db.all`` union — O(entities x claims) work. That is the shape that
bites at GHG scale (60k docs / 800 folders). This establishes a measured
baseline + a generous regression ceiling so "feels slow" becomes a number.
"""

from __future__ import annotations

import time

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from perf_ratchet import record  # noqa: E402
from datetime import datetime

from fichero_server.models.knowledge import (
    ClaimCurationState,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)
from fichero_server.models import DocType, Document

# Library scale to benchmark against. Modest by design so the harness stays
# fast + deterministic; bump these to probe true GHG scale locally.
N_DOCS = 50
N_ENTITIES = 1000
N_CLAIMS = 2000

# Generous ceilings — this is a regression tripwire, not a microbenchmark.
# A blown budget means an algorithmic regression (e.g. an accidental nested
# scan), not normal machine jitter.
FULL_LIST_BUDGET_S = 4.0
DOC_SCOPED_BUDGET_S = 4.0


def _seed_library(db) -> str:
    """Seed N_ENTITIES entities + N_CLAIMS claims across N_DOCS docs.

    Returns one document id usable for the document_id-scoped benchmark.
    """
    now = datetime.now()
    docs = []
    for i in range(N_DOCS):
        doc = Document(name=f"Doc {i}", doc_type=DocType.file)
        db.save(doc)
        docs.append(doc)

    entities = []
    for i in range(N_ENTITIES):
        ent = KnowledgeEntity(
            canonical_name=f"Entity {i}",
            entity_type=EntityType.person,
            aliases=[f"e{i}"],
            source_document_ids=[docs[i % N_DOCS].id],
            created_at=now,
            updated_at=now,
        )
        db.save(ent)
        entities.append(ent)

    for i in range(N_CLAIMS):
        claim = KnowledgeClaim(
            text=f"Claim {i}.",
            source_document_id=docs[i % N_DOCS].id,
            entity_ids=[entities[i % N_ENTITIES].id],
            curation_state=ClaimCurationState.unreviewed,
            confidence=0.9,
            created_at=now,
            updated_at=now,
        )
        db.save(claim)

    return docs[0].id


def test_list_entities_full_scale(client, db):
    _seed_library(db)
    start = time.perf_counter()
    r = client.get("/api/entities?limit=500")
    elapsed = time.perf_counter() - start
    assert r.status_code == 200
    print(
        f"\n[perf] list_entities (full, {N_ENTITIES} ent / {N_CLAIMS} claims): "
        f"{elapsed * 1000:.1f} ms"
    )
    record("entities.list.full", elapsed * 1000)
    assert elapsed < FULL_LIST_BUDGET_S, (
        f"list_entities full-list took {elapsed:.2f}s > {FULL_LIST_BUDGET_S}s "
        "budget — likely an algorithmic regression."
    )


def test_list_entities_doc_scoped_scale(client, db):
    doc_id = _seed_library(db)
    start = time.perf_counter()
    r = client.get(f"/api/entities?document_id={doc_id}&limit=500")
    elapsed = time.perf_counter() - start
    assert r.status_code == 200
    print(
        f"\n[perf] list_entities (document_id-scoped, full claim scan): "
        f"{elapsed * 1000:.1f} ms"
    )
    record("entities.list.doc_scoped", elapsed * 1000)
    assert elapsed < DOC_SCOPED_BUDGET_S, (
        f"list_entities doc-scoped took {elapsed:.2f}s > {DOC_SCOPED_BUDGET_S}s "
        "budget — the claim-scan union is the suspect; profile it."
    )
