# Ontology browser: read the owning library, not the global one — execution plan

Prep for round 2. No code landed; this is the shape, ready to run on confirmation.

## The good news: there is nothing to thread

I expected to add a parameter to ten sheets and touch every call site. That is
not necessary. `libraryServiceEnvironment(_:)`
(`Views/Shell/LibraryServiceEnvironment.swift`) already injects the WINDOW's
library services — `entityService`, `kgCurationService`, `documentStore`,
`apiClient`, `entityStore`, `claimStore` and ~25 more — at every hosting
boundary, and `OntologyBrowser()` mounts inside `ContentView` (
`ContentView+Navigation.swift:174`), under `FicheroApp.swift:809` and
`ContentView+RootLayout.swift:51`, both of which apply it. `SheetLibraryEnvironment`
exists to carry it across sheet boundaries too.

So every one of these views ALREADY has its own library's services in the
environment. It just does not read them. The change is ~13 two-line edits, not
a refactor: add the `@Environment` property, delete the `globalLibrary` line.

## The real count is 13, not 17

The ratchet's 17 over-counts by 4, and the composition is worth recording so
nobody chases phantoms:

- `OntologyBrowser.swift:410,411` — `#Preview` scaffolding. Not runtime.
- `ClaimSummaryCard+Details.swift:308` — `currentLibraryId ?? globalLibraryId`,
  a different and correct pattern (window's current library, global as the id
  default).
- `EntityDetailView+Metadata.swift:11` — a bare `!= nil` existence check, not a
  service read. Still wants fixing (it should check the OWNING library), but it
  reads nothing from the wrong one.

Lower the ratchet as each falls; the target is 2 (the two `#Preview` lines),
at which point the assertion becomes `== 2` with a comment, or the filter
learns to skip `#Preview` bodies.

## Three shapes, thirteen sites

**A. Needs only `entityService`** — read it from the environment and use it
directly. No library resolution at all.

| Site | Call |
|---|---|
| `OntologyBrowser+Toolbar.swift:196,222` | `entityService.…` |
| `EntitySourceGroupsView.swift:207` | `entityService.…` |
| `EntityDetailView+Audit.swift:121,132` | `entityService.…` |
| `EntitySplitSheet.swift:108` | `splitEntity` |
| `EntityMergeSheet.swift:103` | merge |
| `NewEntitySheet.swift:111` | create |
| `ContradictionTriageSheet.swift:245` | claim loads |

**B. Needs something else off the library** — resolve the owning library FROM
the injected service, by identity:

```swift
@Environment(EntityService.self) private var entityService: EntityService?

/// The library this surface is IN — resolved from the service it was handed,
/// by object identity, so it cannot drift the way two notions of "current
/// library" can. nil when it cannot be named: a surface that cannot say which
/// library it is mutating must fail visibly, never fall back (#4306/#4461).
private var owningLibrary: LibraryManager.LibraryReference? {
    entityService.flatMap { LibraryManager.shared.library(owningService: $0) }
}
```

| Site | Needs |
|---|---|
| `ClaimSummaryCard+Details.swift:41,197,214` | `documentStore`, `actionsService` |
| `EntityDetailView+Biography.swift:71` | `documentStore` |
| `OntologyBrowser.swift:356` | `apiClient.currentLibraryPath` |

`actionsService` is deliberately NOT in `libraryServiceEnvironment` and nothing
reads it from the environment, so resolving through the library is the right
route for it — adding a 30th entry to that list for one call site is the
worse trade.

**C. Bare existence check** — `EntityDetailView+Metadata.swift:11`. Becomes a
check on `owningLibrary`, so "no library" means "I cannot name mine", not
"the global one is missing".

## Sequencing — two commits, not thirteen

1. **Shape A (10 sites, 6 files).** All mechanical, all the same edit. Ratchet
   17 → 5 in the same commit.
2. **Shapes B and C (3 files).** The resolver property plus the three
   consumers. Ratchet 5 → 2.

Splitting A from B keeps the mechanical bulk reviewable separately from the
one piece with actual design in it.

## Tests

Per team-lead's brief, every merge / split / create path proves it targets the
NAMED library and fails visibly rather than falling back:

- `LibraryManager.library(owningService:)` returns the vending library for a
  service it vended, and **nil** for one it did not — the fail-visibly
  contract, asserted directly rather than inferred.
- Source-shape guards, one per mutating path (merge, split, create, triage,
  audit, source-groups): the method reads the injected service and contains no
  `globalLibrary` fallback tail. These are the ones that would catch a future
  edit re-adding `?? LibraryManager.shared.globalLibrary` to make a nil go
  away — which is the exact regression that would restore the bug while
  looking like a robustness fix.
- The ratchet lowers with each commit; `DocumentScopeGuardTests` already fails
  if a service is missing from `vendedServices`, so identity resolution cannot
  silently lose a service type.

## Why this matters now

Daniel's dedupe / entity-resolution program (propose-merge-review, after SVO
quality) makes the Ontology browser a primary surface. Merge is the verb that
program is built on, and today merge resolves the reserved-id library. A
propose-merge-review flow shipped on top of that would review proposals from
one graph and apply them to another.
