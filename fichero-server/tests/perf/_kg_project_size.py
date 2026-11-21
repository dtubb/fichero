"""Seed one library at the knowledge store's project size (kg.scale.ratchet-at-project-size).

The shape the store spec's "Measured" section uses: 5,000 pages, 50,000 statements, 12,500 names,
ten statements a page, a few names on very many statements. Every statement names two entities
and carries a verb and an object that is another name's canonical spelling, so the directed graph
build has an edge for every statement. Shared by the KG perf cases in this directory.
"""

from __future__ import annotations

import random
from datetime import datetime

from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import (
    ClaimCurationState,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)

N_DOCS = 5_000
N_CLAIMS = 50_000
N_ENTITIES = 12_500

# The first HOT names are drawn this many times more often than any other, so each sits on
# thousands of statements: the shape where a whole-table scan per question shows.
HOT = 10
HOT_WEIGHT = 500


def seed_project_size(db) -> dict:
    """Write the library into ``db``; return the ids the cases ask about.

    Not cached: the ``client``/``db`` fixtures are function scoped, so every case seeds again.
    """
    rng = random.Random(5261)
    now = datetime.now()

    docs = [Document(name=f"Page {i}", doc_type=DocType.file) for i in range(N_DOCS)]
    db.save_many(docs)

    entities = [
        KnowledgeEntity(
            canonical_name=f"Name {i}",
            entity_type=EntityType.person,
            aliases=[f"n{i}"],
            source_document_ids=[docs[i % N_DOCS].id],
            created_at=now,
            updated_at=now,
        )
        for i in range(N_ENTITIES)
    ]
    db.save_many(entities)

    weights = [HOT_WEIGHT] * HOT + [1] * (N_ENTITIES - HOT)
    picks = rng.choices(range(N_ENTITIES), weights=weights, k=2 * N_CLAIMS)
    claims = []
    for i in range(N_CLAIMS):
        subject = entities[picks[2 * i]]
        obj = entities[picks[2 * i + 1]]
        claims.append(
            KnowledgeClaim(
                text=f"{subject.canonical_name} wrote to {obj.canonical_name} ({i}).",
                source_document_id=docs[i // (N_CLAIMS // N_DOCS)].id,
                source_excerpt=f"...excerpt {i}...",
                entity_ids=[subject.id, obj.id],
                metadata={"verb": "wrote to", "object": obj.canonical_name},
                curation_state=ClaimCurationState.unreviewed,
                confidence=0.9,
                created_at=now,
                updated_at=now,
            )
        )
    # One save_many is one transaction; 50,000 statements in one ran past the per-library DuckDB
    # memory limit the test fixture sets (819 MiB), so the seed commits a chunk at a time.
    for start in range(0, N_CLAIMS, 5_000):
        db.save_many(claims[start : start + 5_000])

    return {"hot_entity_id": entities[0].id, "quiet_entity_id": entities[N_ENTITIES - 1].id}
