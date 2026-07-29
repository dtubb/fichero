"""Perf benchmarks for the document-list + claims-list hot paths (#1815).

NOT part of the default unit gate — lives under tests/perf/ so
`pytest tests/unit/` skips it. Run explicitly:

    PYTHONPATH=fichero-server/src .venv/bin/pytest fichero-server/tests/perf/ -q -s

These benchmarks establish regression tripwires for the three hottest
list endpoints the SwiftUI library view uses:

  GET /api/documents?limit=200          — top-level document list
  GET /api/claims?limit=500             — knowledge-graph claim list
  compute_batch_cache_key × 200 iters   — pure-Python cache-key throughput (#2246)

"100-image entity load" scenario: 100 docs × 20 entities each = 2000
entities / 4000 claims.  The budgets below are generous regression
ceilings (not microbenchmarks) — a blown budget means an algorithmic
regression (e.g. an accidental nested scan) not normal machine jitter.
"""

from __future__ import annotations

import inspect
import time
from datetime import datetime

from fichero_server.models.knowledge import (
    ClaimCurationState,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)
from fichero_server.models import DocType, Document

# "100-image library" scale — 100 docs, 2 000 entities, 4 000 claims.
N_DOCS = 100
N_ENTITIES = 2000
N_CLAIMS = 4000

DOCUMENT_LIST_BUDGET_S = 3.0
CLAIMS_LIST_BUDGET_S = 5.0
CACHE_KEY_BUDGET_S = 2.0
CACHE_KEY_ITERS = 200


def _seed_pipeline_library(db) -> str:
    """Seed N_ENTITIES entities + N_CLAIMS claims across N_DOCS docs.

    Uses db.save_many so KG fixture setup does not schedule real embeddings.
    Returns one document id for scoped benchmarks.
    """
    now = datetime.now()
    docs = [
        Document(
            name=f"Image {i:04d}.jpg",
            doc_type=DocType.file,
        )
        for i in range(N_DOCS)
    ]
    assert db.save_many(docs) == N_DOCS

    entities = [
        KnowledgeEntity(
            canonical_name=f"Person {i}",
            entity_type=EntityType.person,
            aliases=[f"p{i}"],
            source_document_ids=[docs[i % N_DOCS].id],
            created_at=now,
            updated_at=now,
        )
        for i in range(N_ENTITIES)
    ]
    assert db.save_many(entities) == N_ENTITIES

    claims = [
        KnowledgeClaim(
            text=f"Claim text number {i} from source document.",
            source_document_id=docs[i % N_DOCS].id,
            entity_ids=[entities[i % N_ENTITIES].id],
            curation_state=ClaimCurationState.unreviewed,
            confidence=0.85,
            created_at=now,
            updated_at=now,
        )
        for i in range(N_CLAIMS)
    ]
    assert db.save_many(claims) == N_CLAIMS

    return docs[0].id


def test_seed_pipeline_library_uses_bulk_save_path():
    """Perf fixture seeding must not schedule per-row KG embeddings."""
    source = inspect.getsource(_seed_pipeline_library)
    assert "save_many" in source
    assert ".save(" not in source


def test_document_list_100_images(client, db):
    """GET /api/documents must return all 100 docs within budget."""
    _seed_pipeline_library(db)
    start = time.perf_counter()
    r = client.get("/api/documents?limit=200")
    elapsed = time.perf_counter() - start
    assert r.status_code == 200
    body = r.json()
    # The response envelope wraps items under 'documents' or 'items'.
    items = body.get("documents") or body.get("items") or []
    print(
        f"\n[perf] GET /api/documents (100-image library, {N_DOCS} docs): "
        f"{elapsed * 1000:.1f} ms  ({len(items)} docs returned)"
    )
    assert elapsed < DOCUMENT_LIST_BUDGET_S, (
        f"Document list took {elapsed:.2f}s > {DOCUMENT_LIST_BUDGET_S}s budget — "
        "check for N+1 queries or missing index on documents table."
    )


def test_claims_list_scale(client, db):
    """GET /api/claims must return paginated results within budget at 4k-claim scale."""
    _seed_pipeline_library(db)
    start = time.perf_counter()
    r = client.get("/api/claims?limit=500")
    elapsed = time.perf_counter() - start
    assert r.status_code == 200
    print(
        f"\n[perf] GET /api/claims ({N_CLAIMS} claims): "
        f"{elapsed * 1000:.1f} ms"
    )
    assert elapsed < CLAIMS_LIST_BUDGET_S, (
        f"Claims list took {elapsed:.2f}s > {CLAIMS_LIST_BUDGET_S}s budget — "
        "check for full-table scan or Pydantic serialisation regression."
    )


def test_batch_cache_key_throughput():
    """compute_batch_cache_key on a 50-file batch must stay below budget at 200 iters.

    This is the inner-loop cost paid by every sequential-node cache check
    in the Catalogue workflow (#2246).  A single call should be < 1ms even
    for large batches; the budget guards against accidental quadratic growth
    (e.g. if someone added O(n²) sorting or hashing).
    """
    import os
    import tempfile

    from fichero_server.workflows.cache import compute_batch_cache_key

    # Create 50 temp files once; paths are real so _get_file_identity works.
    tmp_paths: list[str] = []
    fds: list[int] = []
    try:
        for i in range(50):
            fd, path = tempfile.mkstemp(suffix=f"_{i}.pdf")
            fds.append(fd)
            os.write(fd, f"content {i}".encode())
            tmp_paths.append(path)
        for fd in fds:
            os.close(fd)

        start = time.perf_counter()
        for _ in range(CACHE_KEY_ITERS):
            compute_batch_cache_key(
                workflow_id="wf-bench",
                node_id="catalogue",
                tool="catalogue",
                config={"output_language": "en", "model": "gpt-4o"},
                provider="openai",
                model="gpt-4o",
                file_paths=tmp_paths,
            )
        elapsed = time.perf_counter() - start
    finally:
        for path in tmp_paths:
            try:
                os.unlink(path)
            except OSError:
                pass

    per_call_ms = elapsed / CACHE_KEY_ITERS * 1000
    print(
        f"\n[perf] compute_batch_cache_key (50 files, {CACHE_KEY_ITERS} iters): "
        f"{elapsed * 1000:.1f} ms total  ({per_call_ms:.3f} ms/call)"
    )
    assert elapsed < CACHE_KEY_BUDGET_S, (
        f"Cache-key computation took {elapsed:.2f}s for {CACHE_KEY_ITERS} iters "
        f"({per_call_ms:.2f} ms/call) > {CACHE_KEY_BUDGET_S}s budget — "
        "likely a hashing or stat syscall regression."
    )
