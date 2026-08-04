# Claim write paths — #4486

**Reading-only analysis. No tests were run.**

## The short answer

**The issue's premise is wrong on both halves, and I think it should be closed
rather than worked.**

`ClaimStore` is not "a store nobody uses": **11 write call sites across 8 view
files** go through it. And the one write that does bypass it loses nothing,
because the server announces the change and the store consumes the
announcement.

What is actually true is smaller and points the other way: **three of the
store's eight write methods have zero callers**, and **one documented rule is
false as written**.

## 1. What rule does `ClaimStore` enforce?

Two, from its own doc comment and its shape:

1. **A view never calls `EntityService` / `KGCurationService` claim methods
   directly** — the store is the single endpoint accessor.
2. **A write is not complete until observable state reflects it.** Every action
   ends in `reload()`, or — for `patch` — an in-place single-row update
   (deliberately, per #4393/#4389: re-fetching 500 rows answers a question the
   server already answered, and re-rendering the list loses scroll and selection
   mid-edit).

It also owns `changeToken`, the monotonic counter that not-yet-store-backed
surfaces (OntologyBrowser's cross-document merge, the inspector's grouped KG
read) observe to resync their own bespoke lists. That is real knowledge the
callers do not have, so rule 1 is not ceremony.

## 2. Who writes claims without going through it?

**One caller.**

| call site | method |
|---|---|
| `KnowledgeGraphInspectorSection+Actions.swift:271` | `kgCurationService.pruneTrivialClaims(scope:)` |

Everything else routes through the store:

| store method | call sites |
|---|---|
| `patch` | 6 |
| `delete` | 2 |
| `setCuration` | 1 |
| `merge` | 1 |
| `link` | 1 |
| **`transition`** | **0** |
| **`batchTransition`** | **0** |
| **`unmerge`** | **0** |

The app has no claim-*create* path at all — there is no `createClaim` in any
Swift service. Claims arrive only from extraction.

## 3. What does the bypass lose?

**Nothing that matters, and I checked rather than assumed.**

- The route (`POST /api/kg/claims/prune-trivial`) goes through the audited
  action layer: `registry.invoke("claim.prune_trivial")`, so **the audit row
  exists**.
- Its `ChangeSpec` sets `emit_type="claim.updated"` when anything was
  suppressed, so **the change is announced**.
- `ClaimStore` is registered on the stream (`LibraryManager.swift:241`,
  `stream.register(self.claimStore)`) and its `apply()` handles `"updated"` by
  bumping `changeToken` and scheduling a reload.

So the store converges, and the surfaces watching `changeToken` resync. The
call site also refreshes its own view state via `loadStatements()`. The only
cost is a redundant fetch, which is not a defect.

**What it does break is rule 1 as written.** The doc says a view *never* calls
those services directly; one view does. That is the familiar shape — a stated
rule and a code path with nothing forcing them to agree — but here the stated
rule is the thing that is wrong, not the code.

## 4. Which direction is right?

**Preserve the store; it is load-bearing.** Unlike #4489, where the writers were
the collapsible side, here the store carries knowledge nothing else has: it is
the change-stream consumer and the source of `changeToken`. Deleting it would
strand the surfaces observing that token.

Two small, independent cleanups — neither urgent:

- **Delete `transition`, `batchTransition`, `unmerge`.** Zero callers. Dead
  write surface on a store whose whole purpose is being the one write path is
  worse than dead code elsewhere: it advertises a route nobody takes, and the
  next person adding a review-queue action will wire one of them up and assume
  it was proven.
- **Then make rule 1 true**, by either adding a `prune` method to the store
  (~10 lines: call the service, `await reload()`) or amending the doc comment to
  name prune as a deliberate exception. I lean to adding the method, because the
  rule is what stops an eleventh caller from drifting — the same argument the
  server-side comment in `extractors.py:2830` makes for emitting from the shared
  write path ("persisting IS announcing").

**Do not do both under one commit as "routing claims through the store"** — the
deletion and the prune method are unrelated changes that happen to touch one
file.

## Interaction with #4499

**None, and I checked because it was asked.** #4499's guarantee — edited claims
survive re-extraction — lives server-side in the curation guard, keyed on
whether page content is user-edited. Nothing proposed here changes claim write
*semantics*; it only changes which Swift object issues an already-audited HTTP
call. Deleting three unused Swift methods cannot reach it.

## Coverage

- **13 claim-write service methods** enumerated across `EntityService+Claims`,
  `EntityService+ClaimEntityCRUD`, `KGCurationService`; callers searched across
  all of `fichero/fichero/`.
- **8 store write methods**, all call sites counted.
- **1 server route + 1 action registration** read end to end for the one bypass.

**What I could not establish by reading, and did not run a suite to settle:**

1. **That `claim.updated` actually reaches the client in practice.** I verified
   the server sets `emit_type` and the client registers the consumer. Whether
   the event survives the transport is a live round-trip question. The whole
   "loses nothing" conclusion rests on it — if the stream is not delivering,
   prune leaves every other claim surface stale until manual reload.
2. **Whether a library-wide prune correctly refreshes a document-scoped store.**
   By reading it should: `apply()` bumps the token and reloads the current
   scope. Confirming needs the app running.

Both are the kind of claim that has been wrong twice today when assumed, so I
am flagging rather than asserting them.
