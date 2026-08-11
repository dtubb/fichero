# Lane audit — outside reader on ~75 commits (2026-08-09)

Read-only audit of `lane/sidebar-ux` since `c3da13c81`, by an agent that did not
write the code. Focus per the brief: the sandbox chain, whether the MAS target
is genuinely untouched, whether tonight's guardrails actually fire, and anything
committed without being built.

Findings are marked **CONFIRMED** (read the code and the mechanism holds) or
**PLAUSIBLE** (reasoned, not proven). Inferences are called out inline.

**Overall: the sandbox work is careful and well-reasoned, and one change in it
materially weakens a security boundary without saying so.** That one is A1.
Everything else is either clean or minor.

---

## A1. CONFIRMED — the bookmark stops being a capability token

`6d60cbf65`, `security/security_scoped_access.py:144-186`.

The change is well motivated and the diagnosis behind it is correct: an
app-scoped bookmark resolves only in the code identity that minted it, the
engine is a different bundle under `com.apple.security.inherit`, so NSURL
resolution fails with error 259 even for good bookmarks. Falling back to "can I
actually read this directory" is a reasonable answer to a real problem, and the
`listdir`-not-`os.access` choice is right and well argued.

The part not stated anywhere in the commit, the docstring, or the tests:

**In the fallback path the bookmark's contents are never examined.**
`start_access_or_inherited` tries `start_access`; if that fails for any reason it
calls `_readable_via_inherited_scope(path)`, which is `os.listdir(path)`, and on
success adds `path` to `_GRANTED` (`:177-184`).

`_GRANTED` is not merely bookkeeping. `granted_paths()` feeds `_granted_roots()`
(`security/path_security.py:316-322`), which is spread directly into the allowed
roots list (`path_security.py:312`). So an entry in `_GRANTED` **becomes an
allowed root**.

The full chain, all confirmed by reading:

1. `POST /api/sandbox/security-scoped-access` with `{path: "<any dir>", bookmark: "<any base64>"}`
   (`api/routes/auth/sandbox_access.py:88-105` — the route does no path validation of its own)
2. → `grant_access` → `start_access_or_inherited`
3. → NSURL resolution fails on the junk bookmark → `os.listdir(path)` succeeds
4. → `_GRANTED.add(path)`, HTTP 200 `granted: true`
5. → that path is now an allowed root for the library-path allowlist and ingest

The security property has changed from *"the user chose this folder and the app
minted a bookmark for it"* to *"the engine process can read this folder"*.

**Severity, honestly:**

- The route is behind the shared-secret auth middleware, which is attached
  separately (`api/main.py:911-913`) and is **not** bypassed by the exemption in
  A2 — that exemption returns `await call_next(request)` rather than
  short-circuiting a response, so everything inside the stack still runs
  regardless of middleware ordering. So this is not remotely reachable and not
  an unauthenticated hole.
- In a **sandboxed** engine (MAS, Release/Dev Embedded), `listdir` only succeeds
  where the kernel already permits — the container plus extensions the app
  turned on. There the fallback's reach is genuinely ≈ "what the app already
  granted", which is exactly the argument the docstring makes. **In that
  configuration the design is sound.**
- In an **unsandboxed** engine — Dev Local, and the DMG channel — `listdir`
  succeeds across the whole home directory. Any caller holding the local token
  can promote *any* readable directory to an allowed root. The allowlist is
  precisely the control that stops an authenticated-but-untrusted local caller
  from pointing the engine at arbitrary directories, and in that channel this
  removes it.

This is defence-in-depth erosion, not an open door. I would not page anyone at
2am for it. I would not ship it to the DMG channel unchanged either.

**Recommended fix, from the change's own argument:** gate the fallback on the
engine actually being sandboxed. The entire justification is "an inherit child
shares the parent's extensions" — in an unsandboxed engine there is no inherited
scope, so the fallback has no rationale there and should not run. There is no
server-side sandbox predicate today (searched: `path_security.py` and `auth.py`
have container-*path* helpers only), so one would need adding — checking whether
`Path.home()` resolves inside `Library/Containers` is the shape the codebase
already reasons in.

**Also worth noting:** the four tests added (`test_security_scoped_access.py`,
the block from `+287`) are good tests that pin the widened behaviour as
*intended*. `test_unresolvable_bookmark_grants_when_directory_is_readable` grants
on a `tmp_path` directory with a `b"stale"` bookmark — that IS the behaviour
above, asserted as correct. The tests are not wrong; they document a decision
whose security consequence was never written down.

---

## A2. CONFIRMED CLEAN — the route exemption is correctly scoped

`aa4267676`, `api/main.py:975-996`. The lead asked specifically about prefix
handling.

`path.startswith("/api/sandbox/")` — with the trailing slash, which is what makes
it safe. `/api/sandboxed-not-really` does not match (it diverges at the `e`), and
that case is pinned by a test. Checked the traversal shapes too:

- `/api/sandbox/../documents` *does* pass `startswith`, so the header check is
  skipped — but Starlette does not normalise `..` in ASGI paths, so routing then
  fails to match any route and returns 404. No route is reached with validation
  skipped. **INFERRED** from framework behaviour rather than tested here; worth a
  test if someone wants it nailed down.
- Percent-encoded variants (`/api/%73andbox/…`) decode before both the check and
  the routing, so they reach the same sandbox route the exemption intends.

Auth is unaffected, as above.

**One forward-looking risk, not a present bug:** the exemption is a prefix, and
the test `test_sandbox_grant_route_is_exempt_from_header_validation` explicitly
asserts `/api/sandbox/anything-future` is exempt — so "every future route under
this prefix skips library-header validation" is now pinned as intended
behaviour. That is a reasonable call today (the sandbox routes genuinely do not
read the header) and a trap the day someone adds `/api/sandbox/read-file`. An
explicit route allowlist instead of a prefix would cost one line per route and
remove the trap.

---

## A3. CONFIRMED CLEAN — the container-tmp allowance stays narrow

`a25626fea`, `path_security.py:248-282`. The lead asked whether the rest of the
Containers tree stays rejected under every path shape.

It does, and the `..` question — my first concern — is handled one level up
rather than in the predicate. `is_sandbox_container_library_staging` is purely
lexical: `Path("…/tmp/x.fichero/../../etc").relative_to(home/"tmp").parts[0]`
ends with `.fichero` and would return True. But its only caller,
`is_allowed_ingest_path` (`:329-357`), builds its candidate list as:

```python
candidates = [resolved]
if ".." not in expanded.parts:
    candidates.append(expanded)
```

so a path containing `..` is only ever tested in its fully-resolved form. The
predicate never sees a traversal. Both shapes (`$HOME/tmp/...` for the sandboxed
engine, `~/Library/Containers/<one>/Data/tmp/...` for the unsandboxed one)
require a single-component container, `Data/tmp` exactly, and a `.fichero`
suffix on the first component under `tmp`. `tmp` itself is not a root. The
docstring's "NEVER relax the single-component container or the suffix" is
correct and load-bearing.

## A4. PLAUSIBLE — a symlink inside a staged package is accepted

Same call site. The un-resolved `expanded` candidate is included whenever the
path has no `..` parts — deliberately, for the iCloud Documents symlink case
(`:331-334`). A consequence: `$HOME/tmp/real.fichero/link → /etc` is accepted by
the predicate via the unresolved candidate, because `parts[0]` is still
`real.fichero`.

Reaching it needs a crafted `.fichero` package (or drop-staging directory)
containing a symlink, and it yields an ingest read rather than anything worse.
**This is pre-existing design, not introduced by `a25626fea`** — the same holds
for the drop-staging and app-support siblings; the new predicate widens the
surface by one more pattern. Flagging it as a class, not as a regression, and I
have not traced whether the downstream reader follows the symlink, so it stays
PLAUSIBLE.

---

## A5. CONFIRMED — the MAS target really is untouched

Every entitlements change in the lane, by diff against `c3da13c81`:

- `fichero/fichero/Fichero.entitlements` (Debug / Dev Embedded) — gains
  `user-selected.read-write`, `bookmarks.app-scope`, `bookmarks.document-scope`
- `fichero/fichero/FicheroRelease.entitlements` (Developer ID / DMG) — gains the
  two bookmark keys

`FicheroAppStore.entitlements` and `FicheroEngineAppStore.entitlements` do not
appear in the diff at all. The claim holds.

The additions are widenings, but to match what the MAS file already carried, and
`bookmarks.app-scope` is what permits minting app-scoped bookmarks at all — the
absence of which was the root cause being fixed. Correct change.

`check_mas_flag_containment` reports the flag gates code in exactly one
allowlisted file (5 gates), so the runtime-gate migration in `cb7c4c5d8` did not
leave strays.

**Minor, least-privilege:** `bookmarks.document-scope` was added to both files,
and I found no document-scope bookmark minting in the app — the `documentScope`
hits in Swift are an unrelated chat/KG concept. The MAS file already carried it,
so this mirrors existing state rather than introducing it, but three targets now
declare an entitlement nothing appears to use, and MAS review dislikes
unjustified entitlements. Worth deleting from all three if the unused finding
holds.

---

## A6. CONFIRMED — the guardrails fire, and mine is the weakest

Four guardrails were added or changed in the lane. I read every fixture rather
than running them: three of the four self-tests mutate real source files, and
running those against a tree another agent is actively editing would be
reckless.

| guardrail | fixture proves firing? | notes |
|---|---|---|
| `check_mas_flag_containment.py:66-85` | **yes, exemplary** | synthesizes clean and dirty inputs in memory, asserts both directions, and encodes a live false positive it caught (a doc comment quoting the directive). No file mutation. |
| `check_embedded_engine_signing.py:47-63` | **yes** | in-memory; also distinguishes *blind* (phase not found) from *clean*, which is the failure mode that matters most here. |
| `check_hang_ratchet.py:154-180` | **yes** | synthesizes a trace table and a stall log, asserts the ratchet fires on regression and passes at baseline. Covers both input formats. |
| `check_environment_forwarding.py:206-…` | yes, **but the weakest of the four** | see below |

**Auditing my own, as harshly as the rest:** `check_environment_forwarding.py`'s
self-test is the only one that proves firing by **writing to real source files**
and restoring them in a `finally`. That is a worse design than the other three
for two reasons. It is not safe under a concurrent writer — exactly the
situation this lane has been in all night, where a restore could clobber another
agent's edit landing in the same window. And a hard kill between write and
restore leaves edited source on disk; the `finally` covers exceptions, not
SIGKILL. The other three synthesize inputs in memory and touch nothing. Mine
should be refactored to do the same — the check's core (`injected_types`,
`boundary_gaps`) already takes text and paths, so it is a small change and I
would take the criticism as valid.

That said, the substance holds: it does fire on both regressions, and they are
reverts of real fixes rather than invented shapes.

---

## A7. Commits landed without a green build — cannot verify, flagging the risk

Building is not in my scope, so I cannot state which commits compiled. What I
can state:

- The lane's own history shows the pattern is real: `0c241be3e` is a build fix
  for `7a189c2b0` ("logger is file-scope, not a member"), i.e. at least one
  commit landed red and was repaired one commit later.
- I observed the tree non-compiling first-hand at 00:04 — `LibraryView.swift`
  referenced `SheetLibraryEnvironment` while that file was still untracked.
  That is a work-in-progress state rather than a bad commit, but it is the same
  hazard: a synchronized-folder target picks files up by presence, so a new file
  that is written but not yet saved/added produces exactly this error.
- `verify_all.sh` plus the 86 guardrails has **not** been run against the lane
  tonight, to my knowledge. Until it is, "the lane is green" is an assumption.

Recommend the gate run be treated as a release blocker for this lane rather than
a nice-to-have, and that the summary line be parsed rather than the exit code —
`0c241be3e` exists because a red state went unnoticed.

---

## What I did not audit

Being explicit so nobody reads more assurance into this than it carries:

- I did not build, run, or execute any test or guardrail.
- I did not audit the ~60 non-sandbox commits individually — only the six named
  plus what the entitlements and MAS-flag checks surfaced.
- A1's severity split between sandboxed and unsandboxed engines is reasoned from
  how `listdir` behaves under the sandbox, not observed on a running system.
- The Starlette path-normalisation behaviour in A2 is framework knowledge, not
  something I tested here.

## Summary

One finding worth acting on before this lane ships: **A1**, the inherited-scope
fallback making the bookmark a non-token, with the DMG channel as the exposed
configuration and a one-condition fix available from the change's own reasoning.

**A2, A3 and A5 are clean** — the prefix exemption is correctly bounded, the
container-tmp allowance stays narrow under every path shape I could construct,
and the MAS target is genuinely untouched. Those three were the ones most likely
to be quietly wrong, and they are not.

**A6**: all four guardrails do fire; the one I wrote has the worst fixture
design of the four and should be brought up to the standard of the other three.

The sandbox work overall is better than most security-adjacent code I have
read — the docstrings argue their own constraints and say which invariants must
never be relaxed. A1 is the one place where a real weakening went unwritten, and
I suspect it went unwritten because the author was reasoning about the sandboxed
engine, where the argument is sound.
