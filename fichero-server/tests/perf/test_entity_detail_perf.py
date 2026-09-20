"""Perf measurement for the entity-DETAIL hot path (#4975).

Companion to ``test_entity_list_perf.py`` (the LIST route). This file covers
what the app calls when a user clicks ONE entity in the Entities table:
``GET /api/entities/{id}/drill-down`` (documents + co-occurrence + excerpts
in one call — see ``EntityService.entityDrillDown`` in Swift) plus the two
sub-routes it bundles, and ``GET /api/entities/claim-counts`` which the
Entities table fetches alongside every list load
(``EntityStore.loadEntities`` calls ``listEntities`` and
``fetchClaimCounts`` concurrently).

NOT part of the default unit gate — lives under tests/perf/ so
`pytest tests/unit/` skips it. Run explicitly:

    PYTHONPATH=fichero-server/src .venv/bin/pytest fichero-server/tests/perf/test_entity_detail_perf.py -q -s

Why this scale: #4975 reports the freeze on an entity with ZERO claims that
appears in ONE document, in a library with thousands of entities/claims — so
the cost must be independent of the answer size. ``N_ENTITIES``/``N_CLAIMS``/
``N_DOCS`` below match the scale the issue names (~10k/60k/1.5k), skewed so
most entities have zero claims and a few hundred have hundreds — exactly the
"0 claims still slow" shape from the issue's evidence screenshot.
"""

from __future__ import annotations

import random
import time
from datetime import datetime

import sys as _sys
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
from perf_ratchet import record  # noqa: E402

from fichero_server.models import DocType, Document
from fichero_server.models.knowledge import (
    ClaimCurationState,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)

N_DOCS = 1500
N_ENTITIES = 10_000
N_CLAIMS = 60_000

# Only entities in this "hot pool" ever get referenced by a claim — every
# other entity (the large majority) has exactly zero claims by construction,
# matching the issue's "0 claims, 1 document" evidence entity.
HOT_POOL_SIZE = 400

# Generous ceilings for Phase 1 — measurement, not yet a ratchet. Phase 2
# tightens these once the fix lands.
DETAIL_BUDGET_S = 4.0

def _seed_library_at_scale(db) -> dict:
    """Seed N_ENTITIES/N_CLAIMS/N_DOCS, skewed, into ``db``.

    Returns a dict with a zero-claim entity id, a hot (hundreds-of-claims)
    entity id, and the shared seed scale. NOT cached across calls: the
    ``client``/``db`` fixtures are function-scoped (a fresh temp DuckDB per
    test), so caching by module would silently seed only the first test and
    leave the rest querying an empty database (caught in review: seeded IDs
    reused against an unseeded db returned near-zero times and a 404).
    """
    rng = random.Random(4975)
    now = datetime.now()

    docs = [Document(name=f"Doc {i}", doc_type=DocType.file) for i in range(N_DOCS)]
    db.save_many(docs)

    entities = [
        KnowledgeEntity(
            canonical_name=f"Entity {i}",
            entity_type=EntityType.person,
            aliases=[f"e{i}"],
            source_document_ids=[docs[i % N_DOCS].id],
            created_at=now,
            updated_at=now,
        )
        for i in range(N_ENTITIES)
    ]
    db.save_many(entities)

    # Skew: claims only ever cite the first HOT_POOL_SIZE entities, weighted
    # so a handful (the first 10) get hundreds of claims each and the rest
    # of the pool gets a light scattering. Every entity beyond the pool
    # (9,600 of 10,000) ends up with zero claims — untouched by any claim.
    weights = [50] * 10 + [1] * (HOT_POOL_SIZE - 10)
    claims = []
    for i in range(N_CLAIMS):
        entity = entities[rng.choices(range(HOT_POOL_SIZE), weights=weights, k=1)[0]]
        doc = docs[i % N_DOCS]
        claims.append(
            KnowledgeClaim(
                text=f"Claim {i} about {entity.canonical_name}.",
                source_document_id=doc.id,
                source_excerpt=f"...excerpt {i}...",
                entity_ids=[entity.id],
                curation_state=ClaimCurationState.unreviewed,
                confidence=0.9,
                created_at=now,
                updated_at=now,
            )
        )
    db.save_many(claims)

    return {
        "zero_claim_entity_id": entities[HOT_POOL_SIZE + 1].id,
        "hot_entity_id": entities[0].id,
        "n_entities": N_ENTITIES,
        "n_claims": N_CLAIMS,
        "n_docs": N_DOCS,
    }


def _time_get(client, path: str) -> tuple[float, object]:
    start = time.perf_counter()
    r = client.get(path)
    elapsed = time.perf_counter() - start
    return elapsed, r


def test_drill_down_cost_is_independent_of_claim_count(client, db):
    """The exact #4975 claim: cost is the ASKING, not the answer size.

    One seeded library, two entities: one with zero claims (the issue's
    "Adolph Lewinson & Sons Inc." shape) and one with hundreds. If the
    route's cost were dominated by rows returned, the zero-claim entity
    would be many times faster than the hot one. Required regression test
    (#4975 Phase 1): asserts the ratio stays bounded (a real "query count/
    cost grows with library size" regression would blow this open) AND
    both stay under the absolute budget.
    """
    state = _seed_library_at_scale(db)

    cold_zero, r = _time_get(client, f"/api/entities/{state['zero_claim_entity_id']}/drill-down")
    assert r.status_code == 200, r.text
    warm_zero, r = _time_get(client, f"/api/entities/{state['zero_claim_entity_id']}/drill-down")
    assert r.status_code == 200

    cold_hot, r = _time_get(client, f"/api/entities/{state['hot_entity_id']}/drill-down")
    assert r.status_code == 200, r.text
    warm_hot, r = _time_get(client, f"/api/entities/{state['hot_entity_id']}/drill-down")
    assert r.status_code == 200

    print(
        f"\n[perf] drill-down ({state['n_entities']} ent / {state['n_claims']} claims): "
        f"zero-claim cold={cold_zero * 1000:.1f}ms warm={warm_zero * 1000:.1f}ms | "
        f"hot(hundreds) cold={cold_hot * 1000:.1f}ms warm={warm_hot * 1000:.1f}ms"
    )
    record("entities.drilldown.zero_claim.cold", cold_zero * 1000)
    record("entities.drilldown.zero_claim.warm", warm_zero * 1000)
    record("entities.drilldown.hot.cold", cold_hot * 1000)
    record("entities.drilldown.hot.warm", warm_hot * 1000)

    for label, elapsed in (("zero-claim", cold_zero), ("hot", cold_hot)):
        assert elapsed < DETAIL_BUDGET_S, (
            f"drill-down ({label}) took {elapsed:.2f}s > {DETAIL_BUDGET_S}s budget"
        )

    # Generous ratio (not a tight ratchet — cold-cache jitter is real): a
    # correctness/perf regression that makes cost scale with claim count
    # would blow well past 20x; noise between two calls a few ms apart
    # will not.
    floor = 0.005  # 5ms noise floor so two sub-millisecond reads can't blow the ratio
    ratio = max(cold_zero, floor) / max(cold_hot, floor)
    assert 1 / 20 < ratio < 20, (
        f"drill-down cost diverges with claim count: zero-claim={cold_zero * 1000:.1f}ms "
        f"vs hot={cold_hot * 1000:.1f}ms (ratio {ratio:.2f}) — expected both dominated by "
        "the same claims-table scan, not by rows returned."
    )


def test_claim_counts_at_scale(client, db):
    """/api/entities/claim-counts — fetched alongside every list-load
    (EntityStore.loadEntities kicks this off concurrently with listEntities).
    Scans every claim's entity_ids column in Python via json.loads + Counter
    (#entities.claim-counts) regardless of what the UI actually needs."""
    state = _seed_library_at_scale(db)

    cold, r = _time_get(client, "/api/entities/claim-counts")
    assert r.status_code == 200, r.text
    warm, r2 = _time_get(client, "/api/entities/claim-counts")
    assert r2.status_code == 200

    print(
        f"\n[perf] claim-counts ({state['n_claims']} claims): "
        f"cold={cold * 1000:.1f}ms warm={warm * 1000:.1f}ms"
    )
    record("entities.claimcounts.cold", cold * 1000)
    record("entities.claimcounts.warm", warm * 1000)


def test_document_inspector_cost_independent_of_library_size(client, db):
    """The REAL reachable path behind '#4975 click freezes': the app never
    calls any /entities/{id}/* route on a table click (verified — grep finds
    zero Swift call sites for entityDrillDown/entityBiography/
    entityCoOccurrence/entityDocuments outside their own definitions, and
    EntityDetailView → getEntityInspector is itself dead code, #4828).

    What DOES run: ``openEntityFromLibrary`` sets ``detailDocument`` to one
    of the entity's source documents, which opens that document's Inspector
    — ``GET /api/documents/{id}/inspector``. Before the #4975 fix, this
    route did ``db.query(KnowledgeClaim)`` (every claim in the WHOLE
    library) + a Python filter, plus ``db.all(KnowledgeEntity)`` (every
    entity) — cost independent of the one document's own claim count,
    exactly the issue's "0 claims, 1 document, still slow" shape, except at
    LIBRARY scale rather than per-entity scale.
    """
    state = _seed_library_at_scale(db)
    # Any one of the 1,500 seeded docs works — each gets only a small share
    # of the 60k claims (spread ~evenly), so its inspector load must not
    # cost anywhere near a whole-library scan.
    r = client.get("/api/documents?limit=1")
    assert r.status_code == 200
    doc_id = r.json()["items"][0]["id"]

    cold, r = _time_get(client, f"/api/documents/{doc_id}/inspector")
    assert r.status_code == 200, r.text
    warm, r2 = _time_get(client, f"/api/documents/{doc_id}/inspector")
    assert r2.status_code == 200

    print(
        f"\n[perf] document inspector ({state['n_entities']} ent / "
        f"{state['n_claims']} claims / {state['n_docs']} docs, one small doc): "
        f"cold={cold * 1000:.1f}ms warm={warm * 1000:.1f}ms"
    )
    record("documents.inspector.small_doc.cold", cold * 1000)
    record("documents.inspector.small_doc.warm", warm * 1000)
    assert cold < DETAIL_BUDGET_S, f"document inspector took {cold:.2f}s > {DETAIL_BUDGET_S}s"


def test_list_entities_app_limit_at_scale(client, db):
    """The Entities table pane's exact request shape: EntitiesLibraryContent
    calls ``store.loadEntities(limit: 25000)`` — the app's real limit, not a
    cleaner smaller one."""
    state = _seed_library_at_scale(db)

    cold, r = _time_get(client, "/api/entities?limit=25000")
    assert r.status_code == 200, r.text
    warm, r2 = _time_get(client, "/api/entities?limit=25000")
    assert r2.status_code == 200

    print(
        f"\n[perf] list_entities app-limit=25000 ({state['n_entities']} ent): "
        f"cold={cold * 1000:.1f}ms warm={warm * 1000:.1f}ms"
    )
    record("entities.list.app_limit_25000.cold", cold * 1000)
    record("entities.list.app_limit_25000.warm", warm * 1000)
