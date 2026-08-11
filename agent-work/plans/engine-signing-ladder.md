# D — engine signing: the executable ladder (APPROVED by Daniel; builds gated by the lead)

**2026-08-08 update — two success criteria per rung, not one.** #4555 (pdfium
`library load disallowed by system policy`) shares the P0's fix locus: the
unsigned engine runs under hardened runtime with NO entitlements, so
`cs.disable-library-validation` never applies. A rung passes only if BOTH
hold:
- **(O1) Library access** — a library outside the container opens; first-ever
  `POST /api/sandbox/security-scoped-access` grants; non-zero
  `librar(ies) granted` at the next spawn.
- **(O2) pdfium loads** — no `library load disallowed by system policy` in
  the engine log on PDF import. CAVEAT: the lead placed the bundled
  kreuzberg/libpdfium.dylib workaround in the staged engine (now durable via
  clean-embedded-engine.sh, commit 6d4959a5b) — if pdfium works, confirm WHY
  before crediting the signing: bundled copy found (workaround) vs a
  tmp-extracted copy loading (library validation actually disabled).

**Definition of done (Daniel):** ⌘R on Dev Embedded works — the signing must
live in the Xcode EMBED PHASE, not only in release scripts.

**Serialization:** before EVERY build, check `GetBuildLog(windowtab2)` for
`buildIsRunning` — Daniel builds in this worktree too.

**MAS phase rules to copy exactly (read from FEED…256, verified):** the
engine is signed IN the embed phase (Xcode's own CodeSign runs after and
seals the outer app); **NEVER `codesign --deep`** — it re-signs nested code
with the PARENT's entitlements, silently replacing the engine's set; the
phase guards that the entitlements file exists before signing. Rung 1's
codesign is therefore the MAS invocation verbatim with the identity swapped,
NOT the --deep form sketched below (superseded).

Gated on Daniel's runtime test of the running build. His outcome decides:
- Creates a library AND opens one outside the container → **skip D entirely.**
- Creates, but outside-container still 403/259 → engine-side `inherit` gap
  confirmed; execute the ladder on evidence.
- Cannot create a library → STOP; that is a C re-diagnosis, not a D problem.

**Revert point: the lane HEAD at execution time** (currently `d89801c7b`;
re-read `git log -1` before starting). Reverting is `git revert <sha>` of the
ladder commits — NEVER reset/checkout/stash in this shared tree. A half-signed
engine state must not survive a failed rung: each rung is one commit, so one
`git revert` restores the known-good app.

MAS is untouched at every rung; `check_mac_app_store_target.py` must stay
green throughout (run it after each rung's commit).

## Rung 1 — Dev Embedded engine signs {app-sandbox, inherit}

**Change:** the non-MAS "Embed Fichero Server" phase (pbxproj object
`CC0011223344556677889903`) gains a codesign step after its copy, mirroring
the MAS phase's invocation but with the dev identity:

```sh
# after the cp -R of "Fichero Server.app" into the app bundle:
codesign --force --deep --sign - \
  --entitlements "$SRCROOT/fichero/FicheroEngineAppStore.entitlements" \
  "$EMBEDDED_ENGINE_APP"
```

(Before writing it: read the MAS phase `FEED00000000000000000256` and copy its
exact codesign form — inside-out vs --deep, identity variable — substituting
identity `-` (ad hoc) for the dev configs. The entitlements FILE is reused
verbatim: {app-sandbox, inherit}, the pair the MAS spike proved runs the full
engine with no cs.* keys and no hardened runtime.)

**Expected observables (in order):**
1. Build green (MCP `windowtab2`).
2. `codesign -d --entitlements - "<built app>/Contents/Resources/Fichero Server.app"`
   prints EXACTLY app-sandbox + inherit.
3. App launches; engine spawns; `/health` answers (engine log present).
4. `Path.home()` in the engine log = the container (unchanged), BUT resolving
   an app-minted bookmark now succeeds — pick an outside-container library:
   no `Code=259` in Console, no `failed_check=roots` for the picked path.

**Failure observables → revert this rung's commit:**
- Engine process dies at spawn (Console: sandbox denial / `EXC_CRASH` with
  entitlement violation; DiagnosticReports .ips naming "Fichero Server").
  That is the inherit-vs-hardened-runtime interaction surfacing at rung 1 —
  record the .ips path in the issue before reverting.
- Build red at the embed phase: codesign refusing the nested bundle → the
  --deep vs inside-out choice was wrong; retry once with the MAS phase's
  exact form before reverting.

## Rung 2 — DMG/Release engine: 6-key combined entitlements

Only after rung 1 holds on this machine.

**Change:** new `fichero/fichero/FicheroEngineSandboxed.entitlements` =
{app-sandbox, inherit} + the four existing cs.* keys from
FicheroEngine.entitlements; `build-release-dmg.sh:112` repoints
`ENGINE_ENTITLEMENTS` at it (Developer ID + `-o runtime` unchanged).

**The unverified claim this rung tests** (flagged INFERRED in the P0 plan):
`inherit` may combine with cs.* hardened-runtime keys (Chromium/Electron
helpers ship this), while it may NOT combine with other sandbox-family keys.
If wrong, the engine aborts at spawn exactly as rung 1's failure mode.

**Expected observables:**
1. `build-release-dmg.sh` completes; `codesign -d --entitlements -` on the
   packaged engine shows all six keys; `codesign --verify --deep --strict`
   green.
2. The packaged app launches ON THIS MACHINE and the engine spawns (weaker
   than a clean-Mac test, but the abort-at-spawn failure shows here too).
3. One-off notarization BEFORE any real release:
   `scripts/notarize.sh build/releases/Fichero.dmg` (submit WITHOUT --wait,
   poll — see notarytool memory), then `spctl -a -t exec` + `stapler validate`.

**Failure → revert rung 2's commit; fallback path:** app carries the cs.*
exceptions itself and the engine keeps exactly the MAS pair — a separate
rung with the same observables, only if rung 2's abort names the cs.* keys.

## Rung 3 — guardrails (only after 1+2 hold)

New `scripts/check_embedded_engine_signing.py`: the non-MAS embed phase must
name FicheroEngineAppStore.entitlements; build-release-dmg.sh must name
FicheroEngineSandboxed.entitlements — each with a `--self-test` that removes
the line and asserts the check FAILS (guardrails prove they fire). Wire into
verify_all --fast.

## Explicitly out of ladder scope
- Item E (duplicate PBXBuildFile entries) — separate quiet-tree commit.
- #4506 tri-state — needs a build + OpenAPI regen; after D settles.
