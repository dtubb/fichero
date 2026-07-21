# GATE 0 — Go/No-Go: does the bundled, signed `lance.duckdb_extension` LOAD inside the embedded + sandboxed Mac app?

**Status:** procedure only — NOT executed here (requires a build; only one xcodebuild allowed and Daniel owns it).
**Verdict gate:** if any step below fails, the `lance`-under-DuckDB plan is DEAD → stay on the `lancedb` Python client. This is the whole risk.
**Date:** 2026-07-21 · Branch: `lance-ext-prep` (see README in this folder).

---

## Why this is the blocker (and why it can't be verified read-only)

`INSTALL lance` fetches the extension binary over HTTP from DuckDB's core-extension repo. **The shipping Mac app is sandboxed and has no outbound-network entitlement to the extension CDN**, and even the non-sandboxed Dev/DMG build must not depend on a network fetch at first run. So the extension MUST be:

1. **bundled** inside the app (a real file on disk inside the app container / Resources), and
2. **`LOAD`ed from that local path** — `LOAD '/abs/path/lance.duckdb_extension'` — not `INSTALL`ed.

Two things must both be true for that `LOAD` to succeed inside the embedded DuckDB:

- **A.** an `osx_arm64` binary of the extension exists for our exact DuckDB version (ABI-pinned).
  - Confirmed available in principle: the extension publishes `osx_arm64` prebuilt binaries (DuckDB core-extension repo; repo `lance-format/lance-duckdb`, latest v0.5.4 / Apr 2026). **Must still confirm the build matches our bundled `duckdb` Python wheel's DuckDB version** — extensions are ABI-locked to a DuckDB version.
- **B.** the embedded DuckDB will actually load that local file under the app's entitlements. Extensions are `dlopen`ed shared objects. Two acceptance paths:
  - **Signed core-repo binary** → loads without `allow_unsigned_extensions`. Preferred: no security relaxation.
  - **Unsigned/locally-built binary** → requires `SET allow_unsigned_extensions=true` on the connection (equivalent of the CLI `-unsigned` flag). Acceptable for Dev but a posture change we do NOT want in the sandboxed MAS build.

Neither A nor B can be observed without building the app and loading the extension inside it. Hence GATE 0.

---

## VERIFIED signing precedent (read this before assuming library-validation kills it)

A peer flagged that the **app** Debug config has `ENABLE_APP_SANDBOX=YES` + `ENABLE_HARDENED_RUNTIME=YES` + library validation. True for the app target — but **the `lance.duckdb_extension` is `dlopen`ed by the embedded ENGINE subprocess (the briefcase CPython that `import duckdb`), NOT the hardened-runtime main app.** The engine is signed with its OWN entitlements, and both channels ALREADY load unsigned third-party native dylibs today. Verified in-repo:

- **MAS / App Store engine** (`fichero/fichero/FicheroEngineAppStore.entitlements`): exactly two keys — `app-sandbox` + `inherit`, **NO hardened runtime, NO `cs.*` keys**. Comment records that the #3746 sandbox spike proved the real 1.0 GB engine (2,889 native libs incl. **duckdb / onnxruntime / lance / pyarrow**) loads with no hardened runtime at all. → macOS **library validation is not enforced on the engine**; a bundled extension `dlopen`s the same way `lance`/`pyarrow` already do.
- **DMG / Developer ID engine** (`fichero/fichero/FicheroEngine.entitlements`): hardened runtime (notarization requires it) **plus `com.apple.security.cs.disable-library-validation = true`**, present explicitly to "load the 800+ third-party native wheels … even though they aren't all signed with our Team ID." → library validation **disabled** here too; the extension loads.
- **Debug** (external engine on :8765): plain dev process, no hardened runtime → least risk.

**Consequence:** macOS library validation is very likely **NOT** the blocker — the same mechanism that already loads `lance`/`pyarrow` `.so`s loads the extension. The real gate collapses to: **(1) DuckDB's OWN extension-signature check** (`allow_unsigned_extensions` — independent of macOS codesigning; a version-matched *signed core-repo* binary passes it, an unsigned local build needs the flag), **(2) ABI version match**, and **(3) the sandbox can read the extension file** from an entitled path (own bundle Resources under `inherit` static rights — confirm the real path). G4/G5 still must be run to prove it end-to-end, but the posture is "expected to pass," not "probably dead."

---

## Pre-flight (can be done WITHOUT the app build — do these first, no xcodebuild)

- [ ] **P1. Pin the DuckDB version.** Read the DuckDB version the bundle actually ships, using the **bundled/embedded** interpreter (briefcase venv), not a dev shell:
  `python -c "import duckdb; print(duckdb.__version__); print(duckdb.sql('pragma version').fetchone())"`
  Record it. The `lance` extension binary MUST target this exact DuckDB version.
- [ ] **P2. Obtain the matching signed osx_arm64 binary.** On a *networked dev machine* with the *same* DuckDB version: `INSTALL lance;` then locate the downloaded file under
  `~/.duckdb/extensions/<duckdb_version>/osx_arm64/lance.duckdb_extension`. That is the signed artifact to bundle.
  - If the core repo has no build for our version → **NO-GO (A fails)** until versions line up: either pin `duckdb` to a version the extension ships for, or wait for the extension to publish ours.
- [ ] **P3. Sanity-load it in a plain (non-app) DuckDB** to prove the file is loadable on this arch, WITHOUT `-unsigned`:
  `duckdb -c "LOAD '/abs/path/lance.duckdb_extension'; SELECT 1;"`
  If this only works with `-unsigned`, the binary is not signed for us → note it (fails B's preferred path).
- [ ] **P4. Confirm the search functions resolve** after LOAD in that plain DuckDB:
  `LOAD '…'; SELECT function_name FROM duckdb_functions() WHERE function_name LIKE 'lance_%';`
  Expect `lance_vector_search`, `lance_fts`, `lance_hybrid_search`. Record the ACTUAL set + signatures — they drive the embeddings rewrite.
- [ ] **P5. Confirm write + index syntax exist** (the docs excerpt omitted CREATE INDEX and row DELETE):
  test `COPY (SELECT 1 id, [0.1,0.2]::FLOAT[2] vec) TO '/tmp/t.lance' (FORMAT lance, MODE 'overwrite');`,
  then whatever `CREATE INDEX … USING IVF_FLAT`/`IVF_PQ` form the loaded extension actually exposes, and probe how row deletion works (rewrite-on-overwrite vs a delete function). Record findings — these are the second-order risks (see RISKS.md §2–3).

## The build gate (Daniel runs the ONE build; agent does not)

- [ ] **G1. Bundle the extension.** Place the signed `lance.duckdb_extension` where the embedded engine can read it at runtime — inside Resources / the sandbox container, on a path the app is entitled to read. Record the absolute runtime path (this is what `_load_lance_extension` LOADs).
- [ ] **G2. Wire `_load_lance_extension(conn)`** (draft: `_load_lance_extension.draft.py`) into `Database._connect()` so every connection LOADs from the bundled path.
- [ ] **G3. Build + launch the Release (sandboxed / MAS-config) app** with the embedded engine.
- [ ] **G4. Inside the running sandboxed app**, exercise a code path that calls `_load_lance_extension` then runs one `lance_vector_search` against a tiny throwaway `.lance` dataset written under the library dir. Observe via engine logs / a debug endpoint.
  - **PASS** = LOAD succeeds AND the query returns AND Console.app shows no sandbox `deny file-read*`/`dlopen` denial on the extension path.
  - **FAIL** = any of: `IO Error: Extension "…" not found`; `Invalid Input Error: Extension … could not be loaded` (ABI mismatch); `not trusted`/unsigned; or a sandbox denial on the extension path or on `dlopen`.
- [ ] **G5. Repeat G4 under the non-sandboxed Dev Embedded build** (strictly easier). If Dev passes but sandboxed fails → the failure is entitlements/sandbox, not the extension.

## Decision matrix

| P2/P3 signed load | G4 sandboxed load | Verdict |
|---|---|---|
| ok | ok | **GO** — proceed to §0.4a steps 1–5 |
| ok | fails (sandbox denies path) | Move bundle to an entitled readable path, retry. NO-GO only if no entitled path works. |
| ok | fails (ABI mismatch) | Re-pin DuckDB/extension versions (P1/P2), rebuild. |
| needs `-unsigned` | — | No signed binary for our version → accept `allow_unsigned_extensions` on **Dev only** and keep the `lancedb` client on MAS, or **NO-GO** for unification. Never ship `allow_unsigned_extensions` in the sandboxed MAS build. |

## Recording the result

Append the outcome (DuckDB version, extension version, runtime path, PASS/FAIL, any Console errors) under a `## Gate-0 run <date>` heading here BEFORE touching the rewrite. Landing the rewrite (steps 1–5) is forbidden until this reads **GO**.
