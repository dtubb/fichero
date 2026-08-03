# #4461 — document-scoped surfaces reaching for `globalLibrary`: full inventory

Taken before any fix, so the fix can be measured against it. Population: every
`globalLibrary` mention in the app target (`fichero/fichero`), 96 lines across
62 files. The question asked of each: **does this surface operate on ONE
document (or one claim/artifact belonging to one document), and does it resolve
its service from that document's library or from the global one?**

## Verdict on the issue's own three

The issue named three sites. One of them is not a defect, and four more exist
that it did not name. Real count: **six**, of which **four are in scope** here.

### 1. `Views/Reader/Knowledge/DocumentKGWebPane+Route.swift:33` — NOT the bug described

The issue reads line 33 alone. Lines 30–32 already resolve the owning library
by `libraryPath`:

```swift
if let match = libraryManager.openLibraries.first(where: { $0.url.path == libraryPath }) {
    return match.ficheroClient
}
return libraryManager.globalLibrary?.ficheroClient   // line 33
```

For a non-global document, `libraryPath` is that library's path and the match
succeeds — the KG route is already correctly scoped. What line 33 actually is
is a **silent wrong-scope fallback**: if `libraryPath` names no open library
(stale path, library closed under the pane), the pane quietly serves the global
library's KG instead of failing. That is the "returns *a* real answer, from the
wrong scope" failure, so it is worth removing — but it is a fallback hardening,
not the translate-shaped error the issue predicted.

### 2. `Views/Inspector/Source/Info/DocumentInspectorInfoTab+Prototype.swift:64,71` — REAL

`DocumentPrototypePicker` lists and assigns document prototypes for
`documentId` through `LibraryManager.shared.globalLibrary?.entityService`,
unconditionally. The issue wondered whether the `+Prototype` filename meant
scaffolding: it does not. `DocumentInspectorInfoTab.swift:203` renders it as
the live "Class" attribute row. In a non-global library the prototype list is
the wrong library's list and the assign call writes to a database where
`documentId` does not exist.

### 3. `Views/Inspector/Knowledge/EntityDigestView.swift:386` — REAL

`EntityDigestContent.docName(for:)` resolves a claim's source-document name out
of `globalLibrary?.documentStore`, while the view already holds an injected
`entityService` that identifies its own library. Non-global documents resolve
to a raw hash id — the quiet-wrong-answer shape, since falling back to the id
is exactly what the function does when the document is genuinely absent.

## Sites the issue did not name

### 4. `Views/Inspector/Source/Info/DocumentInspectorInfoTab+RelatedClaims.swift:81,133` — REAL

`RelatedClaimsPanel(documentId:)`, rendered from the same Info tab
(`DocumentInspectorInfoTab.swift:112`), fetches the document's own claims AND
resolves source-document names from `globalLibrary`. Two reaches, identical
shape to #3, in a file the issue's own scan should have caught — it is the
nearest sibling of a site the issue DID list.

### 5. `Views/Library/LibraryView+InlineEditing.swift:27` — REAL, and the worst of them

Rename-in-place calls `globalLibrary.documentStore.renameDocument(doc,…)` for a
document the user just clicked in whatever library the window is showing. The
same type already owns the correct accessor — `activeLibraryReference`, in
`LibraryView+ContextMenu.swift:40`, window-scoped with a global fallback. This
is a WRITE, not a read: renaming a non-global document runs against the global
database.

### 6. `Views/Library/ViewModes/Graph/Ontology/**` — REAL but DELIBERATELY LEFT

`ClaimSummaryCard+Details.swift:41,197,214,281` and
`EntityDetailView+Biography.swift:71` are claim/document-scoped and reach for
`globalLibrary` unconditionally. They are not being fixed here, on purpose.

They sit inside a cluster of **25 `globalLibrary` lines under
`Views/Library/ViewModes/Graph/`** — `KGMapView`, `KGTimelineView`,
`ForceDirectedGraphView`, `OntologyBrowser` (+`List`/`Toolbar`),
`ContradictionTriageSheet`, `EntityMergeSheet`, `EntitySplitSheet`,
`NewEntitySheet`, `EntitySourceGroupsView`, `EntityDetailView+Audit`,
`EntityDetailView+Metadata` — every one of which resolves global
unconditionally. The Graph view mode is, today, coherently global-only. Fixing
two cards inside it while the browser hosting them stays global produces a
surface with TWO scopes in one window, which is a worse failure than one
consistent wrong one: the card would show a non-global document while the list
beside it showed the global library's. That cluster needs one deliberate pass,
not a drive-by half.

## Deliberately global — correct as written, no change

| Site | Why global is right |
|---|---|
| `Intents/FicheroActionIntents.swift:27`, `Intents/FicheroAppEntities.swift:19,32` | App Intents / Shortcuts entry points. No window, no `WindowState`, no document context to resolve from — global is the only defined scope. |
| `Views/Inspector/Artifacts/ArtifactsInspectorPane.swift:223`, `Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift:98` | `workflowStore`. Workflows are global-only by construction — the sidebar gates them on `libraryId == LibraryManager.globalLibraryId` (`SidebarView+UnifiedLibrarySections.swift:196`). |
| `Views/Settings/**` (LocalModels, Backend, Engine, Share×3, Users, AuditHistory, Snapshots) | App-level configuration, not document work. |
| `Views/Chat/ModelComparison/ComparisonDetailView+Actions.swift:35`, `Views/Shell/iOSLibraryPickerMenu.swift:20`, `Views/Onboarding/FirstRunWindow.swift:54`, `Views/Activity/**` | App-level catalogue / picker / activity surfaces. |
| `Views/Sidebar/SidebarView.swift:249` | A refresh *token* observed to trigger reload — not a data read. |
| `…?? libraryManager.globalLibrary` after a current-library lookup (`LibraryView.swift:628`, `ContentView+SearchResults.swift`, `SidebarItemRow.swift:185`, `SidebarActions.swift`, `SidebarCreationHandlers.swift`, `EditorView.swift:288`, `FocusedDocument.swift:50`, `DocumentInspectorInfoTab.swift:409`, `LibraryView+ContextMenu.swift:44`, `MobileCaptureQueue.swift:192`) | Resolution already happens first; global is the last resort for the case where nothing is open. |
| `LibraryManager.currentLibraryId ?? LibraryManager.globalLibraryId` (`ReadingPaneView.swift:251`, `PDFPageWithToolbar.swift:73`, `ClaimSummaryCardView+Navigation.swift:40,49`, `OntologyBrowser+List.swift:194`, `ClaimSummaryCard+Details.swift:300`) | An *id* default for a navigation payload, not a service reach. |
| `#Preview` bodies (`DocumentInspector.swift:163,178`, `DocumentPickerSheet.swift:287`, `ScheduleEditorView.swift:135`, `TriggerEditorView.swift:215`, `WorkflowExecutionView.swift:335`, `NodePopover.swift:332`, `ActivityLogView.swift:334`, `OntologyBrowser.swift:410,411`, `WorkflowPickerSheet.swift:173`) | Preview scaffolding. Not shipped behaviour. |
| `Models/LibraryManager*.swift` | The definition of global itself. |

## What gets fixed

Sites 1 (fallback removal), 2, 3, 4, 5 — every document-scoped surface whose
surrounding view is already library-scoped. Site 6's cluster is reported, not
touched.
