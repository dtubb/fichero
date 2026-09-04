# The `globalLibrary` sweep (2026-09-04)

`LibraryManager.shared.globalLibrary` is the open library holding the RESERVED
id (`00000000-…-0001`). It is not "the library this window is showing". A
surface that reaches for it while the user is in another library gets *a* real
answer from the wrong scope — no error, no empty state, just facts about a
different database.

Met four times: #4306 (translate ran against the global library's actions
service), #4461 (the KG web pane), and on 2026-09-04 the reader's Node Graph,
the map, and the timeline in one afternoon. This is the sweep that closes it.

## Fixed

| Surface | Symptom |
|---|---|
| `ForceDirectedGraphView` | Node Graph answered "status 404" — the entity id came from the reader's library, the neighbourhood lookup asked Global. |
| `KGMapView` | Empty map over a corpus full of places. |
| `KGTimelineView` | Same, one axis over. |

All three now take the surface's own `EntityService` from the environment,
keeping the old lookup only as a fallback for hosts that inject none.

## Correct as they stand — do not "fix" these

- **App-level settings, onboarding, Snapshots, Sharing, Audit history.** There
  is one global library and these are about it.
- **Intents / AppEntities / MobileCaptureQueue.** No window, so no window
  library. Global is the only defensible default.
- **`x ?? globalLibrary` fallbacks** after a `windowState.libraryId` lookup —
  the sanctioned shape. `ContentView+SearchResults` logs when the fallback
  actually fires, which is the right treatment: degrade, and say so.
- **`WorkflowPickerSheet` lines 23 and 133.** Documented and deliberate
  (#4450): workflow DEFAULTS are global by design and the engine resolves
  default ids against the global library at run time. The sheet asks its own
  library first and falls back only when that store is empty.
- **`#Preview` bodies** (`globalLibrary!`). Preview scaffolding, not a runtime
  path.

## Remaining, and worse than what was fixed — the Ontology browser

17 primary reads across 11 files:

```
3  Claim/ClaimSummaryCard+Details.swift
1  Claim/ContradictionTriageSheet.swift
2  Entity/EntityDetailView+Audit.swift
1  Entity/EntityDetailView+Biography.swift
1  Entity/EntityDetailView+Metadata.swift
1  Entity/EntityMergeSheet.swift
1  Entity/EntitySourceGroupsView.swift
1  Entity/EntitySplitSheet.swift
1  Entity/NewEntitySheet.swift
2  OntologyBrowser+Toolbar.swift
3  OntologyBrowser.swift
```

These are worse than the three fixed above because most of them **mutate**:
merge, split, create, triage, audit. A read against the wrong library is an
empty view; a merge against the wrong library is a write somewhere the user
was not looking, in a database whose entities they never chose.

**Not fixed on 2026-09-04, deliberately.** None of these views holds an
injected service, so the fix is not a one-line swap — it is threading a
service (or the library) through each sheet's call sites, across 11 files,
during an active compile pass and with no way to build. That is how a sweep
turns into an outage.

### The fix, when it is taken

`LibraryManager.library(owningService:)` already exists for exactly this
(added for #4306/#4461). It matches by object IDENTITY — the service object a
view holds IS the one its library built — so it cannot drift the way two
parallel notions of "current library" can, and it returns nil rather than
falling back to global, because a caller that cannot name its library should
fail visibly rather than quietly operate on another one.

So: inject the service the sheet already needs, resolve the library from it,
and delete the `globalLibrary` line. One file at a time.

### The ratchet

`OwningLibraryScopeTests` pins two things: the three fixed surfaces must not
reacquire a primary read, and the Ontology directory's count may fall but
never rise. Fix one, lower the number in the same commit. When it reaches
zero, delete the ratchet and add the directory to `cleanedSurfaces`.
