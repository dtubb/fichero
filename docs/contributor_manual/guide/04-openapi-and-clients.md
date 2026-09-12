# 4. OpenAPI and Clients


Fichero’s API contract flows in one direction:

1.  Pydantic models and FastAPI route signatures define the backend schema.
2.  The engine exports `openapi.json`.
3.  The schema is synced into the local Swift package.
4.  Apple Swift OpenAPI Generator produces the typed client.
5.  The Swift app calls that generated client through hand-written wrappers.

The important files:

- backend app entry: `fichero-server/src/fichero_server/api/main.py`
- contract snapshot: `fichero-server/tests/contracts/openapi.json`
- sync script: `fichero-server/scripts/sync_openapi_schema.sh`
- generated Swift package: `fichero/fichero-api-client/`

There are two layers on the Swift side: **generated code** in `fichero/fichero-api-client/`, and **hand-written service wrappers** in `fichero/fichero/Services/*Service.swift` (e.g. `DocumentService.swift`, `SearchService.swift`, `WorkflowService.swift`). The wrappers are where most real frontend API work happens. Never hand-edit the generated package — the `openapi.json` files are regenerated from the backend and that regen output is committed; what is forbidden is editing them by hand.

Run the sync whenever you change route signatures, request/response models, enum values, or field names/optionality that affect the schema:

    ./fichero-server/scripts/sync_openapi_schema.sh

Skip it and the Swift app drifts from the contract and usually fails to build. Commit the regenerated artifacts in the same change set as the API change.

### Pydantic field discipline

Several failure modes bite *silently* — no exception, no test failure, just data that vanishes:

1.  **Declare every field on the Pydantic model.** `extra="allow"` lets unknown fields write at runtime, but `model_dump()` only serializes declared fields, so the next read drops them. Add the DB column, the model field, and the OpenAPI-typed schema field in the same commit.
2.  **Swift wrappers set OpenAPI-typed fields, never** `additionalProperties`**.** Declared fields dumped into `additionalProperties` round-trip on the wire but the backend Pydantic model ignores them — the write is lost.
3.  **Endpoint defaults matched by strict equality against seed data are foot-guns.** Default `Optional[T] = None`, filter only when the caller passes a value, add a regression test.
4.  **A closed set of values is an enum in the schema, never a bare** `str`**.** A `str` field generates a Swift `String`, both sides write literals, and nothing objects — that is how `artifact_type` produced a dead feature from two green commits (#4418). Declared as an enum, the mismatch becomes a compile error.
5.  **A structured payload is a typed field, never** `dict[str, Any]`**.** If it has a shape, declare the shape (#4396).

Prefer *impossible* over *checked* over *documented*. A generated type cannot drift; a guardrail can fail open; a convention can be forgotten.

Also: **timestamps are aware UTC.** Write `fichero_server.core.timeutil.utc_now()`, never `datetime.now()` / `datetime.utcnow()`. Open DuckDB connections with `fichero_server.core.duckdb_session.connect_utc` and treat naive stored values as UTC through `ensure_utc()`. `scripts/check_naive_datetimes.py` fails the gate on the naive forms.

### Closing note: the extensibility guarantee

The backend treats new extraction outputs as additive in 0.0.x; the contract test is `fichero-server/tests/contracts/test_extensibility_guarantee.py` (#1652). Guaranteed additive extension points: new entity-type keys are data (`ClassificationValue` + `LibraryEntityType`), not schema; SVO predicates (`KnowledgeClaim.predicate_verb`) are open strings; new extraction products land as new `Artifact.artifact_type` string values; annotation motivations live in free-form metadata; `Document`, `KnowledgeEntity`, `KnowledgeClaim`, `Annotation`, and `Note` use `extra="allow"` so added response fields do not break decode; and `Database._ensure_table()` issues idempotent `ADD COLUMN` statements for newly declared model fields, so additive schema growth needs no hand-written migration. Known gaps (tracked under \#1652): first-class `entity_type` and `quotation_kind` values are still enum-backed.
