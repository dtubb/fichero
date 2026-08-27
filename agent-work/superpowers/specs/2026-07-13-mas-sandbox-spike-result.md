# MAS sandbox spike — RESULT (#3746)

Date: 2026-07-13 · Spike, not a feature. Deliverable is knowledge.
Verdict: **GO — all four questions are YES.** The engine runs, loads its native wheels, writes DuckDB, and **serves HTTP requests from inside an inherited App Sandbox.**

This is the empirical answer to Open Question #1 of `2026-07-13-mac-app-store-sandbox-research.md` ("nobody has yet proven Fichero's specific CPython+800-wheels engine runs inside an inherited sandbox"). It now has been.

---

## ⚠️ BUILD REQUIREMENT — do not sign the outer app with `--deep`

**This is a build-script requirement, not a footnote. Getting it wrong silently produces a bundle that violates Apple's two-key rule and will be aborted at runtime or rejected at ingestion — with no error at signing time.**

`codesign --deep` **re-signs nested code with the OUTER app's entitlements.** Run it on the app and it will overwrite the engine's `app-sandbox` + `inherit` pair with the app's five-key MAS entitlements — and Apple's rule is that *any* App Sandbox key beyond those two causes the system to **abort the child**. The signature still "succeeds"; nothing warns you.

The correct order, which this spike used and verified:

```bash
# 1. Sign the ENGINE FIRST, with EXACTLY the two keys.
codesign --force --deep --sign "$ID" \
  --entitlements child.entitlements \
  "Fichero.app/Contents/Helpers/Fichero Server.app"

# 2. Sign the OUTER app WITHOUT --deep, so it cannot touch the child.
codesign --force --sign "$ID" \
  --entitlements FicheroAppStore.entitlements \
  "Fichero.app"

# 3. VERIFY AFTER SIGNING — assume nothing. Must print exactly two keys.
codesign -d --entitlements :- "Fichero.app/Contents/Helpers/Fichero Server.app"
#   com.apple.security.app-sandbox
#   com.apple.security.inherit
```

Also required for the helper: `CODE_SIGN_INJECT_BASE_ENTITLEMENTS = NO` — Xcode injects `get-task-allow`, which is incompatible with `inherit`. (This spike signed by hand, so the injected key never appeared; verified `get-task-allow` count = 0.)

Tracked as a packaging requirement in **#3749**.

---

## What was actually run

A **sandboxed parent** (`Parent.app`, signed with the same five keys as `FicheroAppStore.entitlements`: `app-sandbox`, `network.client`, `network.server`, `files.user-selected.read-write`, `files.bookmarks.app-scope`) spawns the **real Briefcase engine** via `Foundation.Process` — the same mechanism `EmbeddedBackendService.launchEmbeddedBackend()` uses.

The engine is the genuine article, built with `fichero-server/scripts/build_backend_bundle.sh`: **1.0 GB, 361 bundled `.so` extensions**, including `_duckdb`, numpy, lance, onnxruntime, PyMuPDF.

The engine is signed with **exactly the two keys**, per Apple's rule that any other App Sandbox key aborts the child:

```
com.apple.security.app-sandbox
com.apple.security.inherit
```

Verified after signing (`codesign -d --entitlements`): exactly those two, **zero** `get-task-allow` (so the `CODE_SIGN_INJECT_BASE_ENTITLEMENTS = NO` requirement is satisfied — I signed by hand, and Xcode's injected entitlement never appeared). Signed **without hardened runtime** (`flags=0x0(none)`) and **without any `cs.*` exception** — deliberately, to emulate the MAS trust path rather than the DMG one.

Order matters: the engine is signed **first**, then the parent is signed **without `--deep`**. Signing the parent with `--deep` overwrites the nested child's entitlements with the parent's — which would silently break the two-key rule.

---

## The four questions

### 1. Does CPython launch at all under inheritance? — **YES**

```
Q1_SPAWN: process started, pid=40878
2026-07-13 20:48:13 - __main__ - INFO - Starting Fichero Backend (Briefcase bundle)
```

### 2. Do the native wheels load? — **YES, and `disable-library-validation` was NOT needed**

`lsof` on the **live sandboxed process**: **2,889 native libraries mapped**. Confirmed present:

| wheel | mapped in the sandboxed process |
|---|---|
| duckdb | ✓ |
| numpy | ✓ |
| onnxruntime | ✓ |
| lance | ✓ |
| tokenizers | ✓ |
| pyarrow | ✓ |

**This answers Open Question #2 (`cs.*` entitlements at MAS).** `com.apple.security.cs.disable-library-validation` is a **hardened-runtime** exception. The child here runs with **no hardened runtime and no `cs.*` keys at all**, and 2,889 third-party dylibs — none signed with our Team ID — loaded anyway. Library validation is not enforced in this configuration, so **the `cs.*` entitlements appear unnecessary for the MAS engine.** Keep them for the DMG channel (notarization), drop them from the MAS engine profile.

*Not exercised:* PyMuPDF (`fitz`) is bundled but lazily imported, so it never mapped during a bare startup. It is the same class of unsigned third-party wheel as the six above, and library validation is a process-wide flag — if it were enforced, the *first* unsigned dylib would have failed, not the 2,889th. Low risk, but it is inference, not measurement. Exercise a PDF import path to close it.

### 3. Does DuckDB open and write a library file? — **YES**

`GET /api/documents` with `X-Fichero-Library-Path` → **HTTP 200**, returning the seeded `Inbox` node. On disk, inside the container:

```
~/Library/Containers/app.fichero.spike/Data/Library/Application Support/Fichero/
  SpikeLibrary.fichero/fichero.duckdb   4,730,880 bytes   ← library DB, written by the sandboxed engine
  app.duckdb + app.duckdb.wal                             ← app-wide DB
  .api-key  (mode 0600)                                   ← bootstrap token adopted
```

A first attempt returned **HTTP 403** — but that was **Fichero's own** `_is_allowed_library_path` validation (the path wasn't a `.fichero` package), **not a sandbox denial**. Worth recording: `_is_allowed_library_path` *already* whitelists the sandboxed host app's container Application Support (`api/main.py:952-954`), so a container-local library works today with no engine change.

### 4. Does the loopback bind succeed with `network.server`? — **YES**

```
INFO: Uvicorn running on http://127.0.0.1:8765
Q4_SERVE: HTTP 200 from loopback — {"status":"healthy", ...}
```

The sandboxed parent made a real HTTP request to the sandboxed child and got a 200 back. **The engine served a request from inside the sandbox.**

---

## Proof the child was genuinely sandboxed (not merely entitled)

Two independent confirmations, either of which alone would be weak:

1. **The child's `HOME` was container-redirected.** The engine wrote to `~/Library/Containers/app.fichero.spike/Data/...`, not to the real `~`. Only a sandboxed process gets that redirection — and it inherited the *parent's* container, which is exactly what `inherit` means.
2. **A pre-nesting attempt failed with a sandbox denial.** With the engine sitting in `/tmp`, the sandboxed parent could not even spawn it:
   `Error Domain=NSCocoaErrorDomain Code=4 "The file "Fichero Server" doesn't exist"` — the file plainly existed; the sandbox denied the read. Moving the engine **inside the parent bundle** (`Contents/Helpers/`) fixed it.

**No sandbox denials were logged during the successful runs.**

---

## Findings beyond the four questions

**A. The helper MUST be nested inside the app bundle.** Demonstrated above, not inferred. This corroborates risk #3 in the research doc (nested-code placement): the engine must move out of `Contents/Resources` into `Contents/Helpers`, and `EmbeddedBackendService`'s path must follow.

**B. The engine performs NETWORK EGRESS AT STARTUP — flag for review.** It pre-warms an embeddings model and downloads it from Hugging Face on launch:

```
INFO - Pre-warming embeddings model: fichero-pinned/multilingual-e5-large-mean-v1
HTTP Request: GET https://huggingface.co/api/models/Qdrant/multilingual-e5-large-onnx "200 OK"
→ cached to <container>/.cache/huggingface
```

This *worked* in the sandbox (the container cache is legal, and `network.client` inherits). But for MAS it is worth a deliberate decision: model **weights are data**, permitted under 4.2.3(ii) *with disclosure* — they are not executable code, so 2.5.2 is not implicated. The real problems are practical: a **first-run network dependency**, a silent multi-hundred-MB download, and offline launches. Recommend bundling the pinned model or making the pre-warm lazy/opt-in for the MAS SKU.

**C. `cs.*` entitlements are not needed for the MAS engine** — see Q2. This closes Open Question #2 in the research doc.

**D. `--deep` signing is a trap.** Signing the outer app with `--deep` re-signs nested code with the *parent's* entitlements, silently violating the two-key rule. The build must sign inner-first, outer without `--deep`.

---

## What this does NOT prove

Honesty about scope — the spike answers the *gating* question, not every question:

- **Security-scoped bookmarks are still unaddressed.** The library here lived *inside the container*, which needs no bookmark. A user's real library in `~/Documents` does: dynamic file grants do **not** inherit into the child (Apple-documented). This remains the largest piece of real work (research doc, risk #2) and it is untouched by this result.
- **The orphan-sweep machinery** (`pgrep` / `ps -E` / `lsof` / `kill` of non-children) was not exercised; it lives in the Swift app, not the engine. Research doc's Open Question #4 stands.
- **MAS ingestion validation** (ITMS) was not tested — that needs a real upload.
- PyMuPDF import (see Q2).

---

## Recommendation

**Option A (one app, embedded engine) is viable — proceed.** The gating unknown is now resolved in its favour: our specific CPython + native-wheel engine runs, opens DuckDB, and serves HTTP inside an inherited App Sandbox with exactly the two permitted entitlement keys and no hardened-runtime escapes.

The remaining Option A work is engineering with known shapes — bookmark plumbing, moving the nested app to `Contents/Helpers`, lifecycle rework, target split — not an unknown. Option B (two apps) stays the designed fallback, but nothing in this result forces it.

## Reproducing

Harness lives in `/tmp/f_spike` (throwaway, not committed): `parent.swift` + `parent.entitlements` (5 keys) + `child.entitlements` (exactly 2). Build the engine with `fichero-server/scripts/build_backend_bundle.sh`, nest it at `Parent.app/Contents/Helpers/`, sign inner-then-outer (no `--deep` on the outer), and run the parent with the engine path and port 8765.
