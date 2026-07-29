<!-- Verified against scripts/sync_openapi_schema.sh + repo layout (2026-07-18): all paths and the contract flow are accurate. -->

# OpenAPI and Generated Clients

## Table of Contents

- [The Contract Path](#the-contract-path)
- [What Is Generated and What Is Hand-Written](#what-is-generated-and-what-is-hand-written)
- [Why Pydantic Field Discipline Matters](#why-pydantic-field-discipline-matters)
- [When To Regenerate](#when-to-regenerate)

## The Contract Path

Fichero's API contract flows in one direction:

1. Pydantic models and FastAPI route signatures define the backend schema.
2. The engine exports `openapi.json`.
3. The schema is synced into the local Swift package.
4. Apple Swift OpenAPI Generator produces the typed client.
5. The Swift app calls that generated client through hand-written wrappers.

In this repo, the important files are:

- backend app entry: `fichero-server/src/fichero_server/api/main.py`
- backend contract snapshot: `fichero-server/tests/contracts/openapi.json`
- sync script: `fichero-server/scripts/sync_openapi_schema.sh`
- generated Swift package: `fichero/fichero-api-client/`

## What Is Generated and What Is Hand-Written

There are two layers on the Swift side:

- generated code in `fichero/fichero-api-client/`
- hand-written wrappers in `fichero/fichero/Services/*Generated.swift`

The `*Generated.swift` suffix on the app side is misleading. Those wrapper files are hand-written and editable. The truly generated code lives in the local Swift package built from `openapi.json`.

That separation matters because most real frontend API work happens in the wrappers, not in the generated package.

## Why Pydantic Field Discipline Matters

This codebase has a specific failure mode around Pydantic and OpenAPI:

- if a field exists in storage but is not declared on the Pydantic model, it can disappear on serialization
- if Swift writes declared schema fields into `additionalProperties` instead of the typed OpenAPI field, the backend may silently ignore them

For contributors, the rule is strict:

- add the backend model field
- add the DB column support
- expose the typed OpenAPI field
- update Swift to use the typed field, not `additionalProperties`

This is not style guidance. It is how you avoid silent data loss.

## When To Regenerate

Run the sync script whenever you change:

- route signatures
- request or response models
- enum values
- field names or optionality that affect the schema

Use:

```bash
./fichero-server/scripts/sync_openapi_schema.sh
```

If you skip that step after an API change, the Swift app will drift from the backend contract and usually fail to build or behave incorrectly.
