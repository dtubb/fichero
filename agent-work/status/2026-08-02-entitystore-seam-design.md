# EntityStore: the seam, designed before it is built (#4489)

Report only. Nothing implemented.

---

## 1. The four containers — and two of them are one thing

| | container | what it is for | **production readers** |
|---|---|---|---|
| C1 | `entities` | legacy mirror of the *current* document scope | **none** |
| C2 | `libraryEntities` | the ontology browser's list | `OntologyBrowser.swift:234` |
| C3 | `libraryClaimCounts` | `[entityId: Int]` beside C2 | `OntologyBrowser.swift:237` |
| C4 | `entitiesByDocumentId` | per-document buckets | inspector (`+Scope.swift:55` via `entities(forDocument:)`), reader (`DocumentKGSurface.swift:210`), strip (`DisplayAttributesStrip.swift:98`) |

**C1 has no production reader.** Not one. `entityStore.entities` appears nowhere in `Views/`, `Services/` or `App/` — every hit for "entities" in those trees is the `KGSurfaceTab.entities` enum case. The inspector, which is the surface C1 was presumably written for, reads C4 through `entities(forDocument:)`.

C1 is also not independent state: `syncLegacyScope` (`+ChangeEvents.swift:26`) does

```swift
entities = entitiesByDocumentId[documentId] ?? []
```

so it is a **projection of C4 for one scope**, recomputed on every load path (six call sites in `+Loading.swift`).

**So the answer to "are two of them the same thing" is yes, and the fix is smaller than a seam.** C1 is dead state that three mutations spend code keeping up to date, and that one test asserts.

## 2. Does one seam serve all four?

**After deleting C1, a seam is barely needed** — which is the useful shape of the answer.

What remains is three containers with genuinely different scopes:

- C4 is per-document. Every mutation that changes an entity's fields must patch **every bucket the entity appears in** (an entity is referenced by many documents).
- C2 is library-wide, a different query result.
- C3 is a count map keyed by entity id, and only **membership** changes it — delete prunes, merge should.

A seam modelled on `updateLocal` — `patchEntity(_ entity:)` that writes C4 buckets and C2, plus `removeEntities(_ ids:)` that writes C4, C2 **and** C3 — covers every mutation in the store. Two functions, not one, because the count map is only touched by membership: making every record-patch also touch C3 would be the "seam that does too much" failure.

**Mutations that legitimately touch a subset**, which the seam must not force:
- `setExternalAuthorityEnabled` — a scalar flag, no container.
- `reconciliationCandidates` / `refreshAuthorityCandidates` — reads.
- `rename` — a record change; touches C4 + C2, correctly not C3.

That is the `renameDocument` case you named: the seam allows a record-only path, but the default is the complete one.

## 3. Which of the four are LIVE bugs — the question that matters

| # | gap | container missed | read by anything? | verdict |
|---|---|---|---|---|
| ① | `setCuration` doesn't patch C4 | **C4** | **yes — the inspector** | **LIVE** |
| ② | `apply(_:)` "deleted" removes from C1 only | C2, C3, C4 | **yes — all three** | **LIVE** |
| ③ | `merge` skips C3 | **C3** | **yes — the browser** | **LIVE** |
| ④ | `reload()` never refreshes C2/C3 | C2, C3 | **yes — the browser** | **LIVE** |
| — | every mutation's C1 patch | C1 | **no** | **dead state — delete it** |

So: **four live gaps, and none of them is the one I first reported.**

My earlier repro for ① was wrong in its mechanism and I am correcting it. I said the badge appears and then reverts when you switch documents and back. It does not appear in the first place: the inspector reads C4, `setCuration` writes C2 and C1, and **the caller does no reload** — `DocumentInspectorEntitiesTab+Actions.swift:112-127` invokes it, sets a success message, and stops.

Whether a user sees anything therefore depends on the change stream repairing it out of band (`apply` → `scheduleReload` → refetch of document scopes). Which means the optimistic patch is either **redundant** (the stream repairs it) or **wrong** (it does not) — and never right. That is the honest statement, and it is worse than a simple revert: the code depends on the push channel for the correctness of its own local update.

**And the test that covers `setCuration` asserts C1** (`EntityStoreTests.swift:153`) — the container with no readers. It is green, it is meaningful-looking, and it checks the one place that cannot affect anyone.

## 4. Recommended order

1. **Delete C1** and `syncLegacyScope`'s assignment to it. This removes three partial reconciliations by removing the thing being partially reconciled, and deletes the misleading test. Smallest change, largest reduction in surface.
2. **Introduce the two seam functions** and route the remaining mutations through them.
3. **Fix ③ and ④** as part of routing — they are one-line omissions once there is one place to omit them from.
4. **Fix ② by making `apply` use the same seam as local `delete`**, which is what makes push and local agree about what "deleted" means rather than agreeing by inspection.

Tests: `placements`-style counting adapted to entities — one helper that gathers every container an entity id appears in, plus its claim-count entry, so "did this mutation reach everywhere" is one assertion rather than four. With its own test proving it can see a disagreement.

## 5. The general rule this supports

The risk was predictable from the type declaration. One container cannot disagree with itself; four can, and did, four times. `ClaimStore` (one container), `AnnotationStore` (one container) and `KGQueryStore` (no mutations) are clean because there was nothing to keep in agreement — not because anyone was more careful.

**"Audit the stores" reduces to "count the containers."** And a container with no readers is not a container to reconcile — it is one to delete.
