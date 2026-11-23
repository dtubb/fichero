import SwiftUI

// MARK: - ContentView Compact (iPhone) Reader Extension
// Agent: ViewBuilderAgent
// Responsibility: Compact-width forward navigation (#2551) — the library/search
// list → reader push stack, and the shared compact list→detail stack helper.
// Split out of ContentView+ViewBuilders.swift to keep each file under the
// file_length limit.

extension ContentView {
    // MARK: - Compact (iPhone) forward navigation (#2551)

    /// True only on COMPACT width for the library/search modes that own the
    /// list → reader pipeline (#2551). macOS/iPad-regular return `false` (the
    /// split layout is used instead, untouched). The entities browser is
    /// excluded — it drives the KG focus state, not a document reader.
    /// Internal (not private): referenced from ContentView+SidebarLayout.swift's
    /// `centerContentRouting` — `private` is file-scoped.
    var usesCompactReaderFlow: Bool {
        CompactShellPolicy.route(
            horizontalSizeClass: horizontalSizeClass,
            appViewMode: viewMode,
            isEntitySelection: isEntityLibrarySelection
        ) == .libraryReader
    }

    /// Resolves the current selection to a LEAF document for the compact reader
    /// push (#2551) — never a folder, so tapping a folder still drills in place.
    /// Falls back to the current selection when no promoted `detailDocument`
    /// exists (the .none/.standard promote policy is regular-width only). Resolves
    /// from the DISPLAYED documents first, then `currentDocuments`, so a tap
    /// resolves even when those two momentarily disagree (#2666).
    /// nonisolated static so the truth table is testable off-main — View statics
    /// inherit the type's MainActor isolation under the macOS 26 SDK (#4201).
    nonisolated static func resolveCompactReaderLeaf(
        detailDocument: Document?,
        selectedId: String?,
        displayedDocuments: [Document],
        fallbackDocuments: [Document]
    ) -> Document? {
        let candidate = detailDocument
            ?? selectedId.flatMap { id in
                displayedDocuments.first(where: { $0.id == id })
                    ?? fallbackDocuments.first(where: { $0.id == id })
            }
        guard let doc = candidate, !doc.isNavigableContainer else { return nil }
        return doc
    }

    private func compactReaderLeaf() -> Document? {
        Self.resolveCompactReaderLeaf(
            detailDocument: detailDocument,
            // Document-order primary, never Set.first (F3, 2026-08-09).
            selectedId: shellPrimarySelectionId(
                in: browserSelection, orderedBy: documentStore.currentDocuments
            ),
            // The SAME array LibraryView is showing: transient-search hits can
            // live outside the browsed folder, so resolving only from
            // `currentDocuments` left search-result taps unresolvable (#2666).
            displayedDocuments: activeSearchQuery == nil
                ? selectedDocuments
                : searchResultDocuments,
            fallbackDocuments: documentStore.currentDocuments
        )
    }

    /// Puts the resolved leaf on the path as its item (#2666, #6944). A leaf that resolves to nothing pops nothing:
    /// only Back removes a pushed item.
    private func syncPushedReaderDocument() {
        guard let leaf = compactReaderLeaf() else { return }
        if pushedReaderDocument?.id != leaf.id {
            pushedReaderDocument = leaf
        }
        windowState.compactPath.open(item: leaf.id)
    }

    /// A folder, a group or a PDF tapped in a list: at compact width its screen is pushed on the path, so Back
    /// returns to the list it was tapped in (`ios.nav.folders-push`, #6945).
    func navigateIntoFolder(_ doc: Document) {
        if usesCompactReaderFlow {
            let selected = sidebarSelectionState.selectedItemId
            let current = selected.map { $0.hasPrefix("doc:") ? String($0.dropFirst(4)) : $0 }
            windowState.compactPath.pushFolder(doc.id, from: current)
        }
        navigateToDocument(doc)
    }

    /// Back from a folder screen re-roots the shared list on the folder now on top.
    private func showCompactFolder(_ folderId: String?) {
        guard let folderId, sidebarSelectionState.selectedItemId != "doc:\(folderId)",
              let doc = documentStore.resolveDocument(folderId) else { return }
        navigateToDocument(doc)
    }

    /// The path's binding for the stack: a pop writes a shorter path back.
    private var compactPathBinding: Binding<[CompactStep]> {
        Binding(
            get: { windowState.compactPath.steps },
            set: { windowState.compactPath.set($0) }
        )
    }

    /// Compact (iPhone) library/search reader stack (#2551). The list is the
    /// root; selecting a leaf document pushes the reader — the SAME `previewView`
    /// EditorView the regular content pane shows in its preview slot, so there is
    /// no parallel reader. `NavigationStack` supplies the Back affordance.
    /// Internal (not private): referenced from ContentView+SidebarLayout.swift's
    /// `centerContentRouting` — `private` is file-scoped.
    @ViewBuilder
    var compactLibraryReaderStack: some View {
        NavigationStack(path: compactPathBinding) {
            // AnyView is load-bearing (#4331): this iPhone-only stack sits at the
            // deepest point of the shell's getter chain — erasing here keeps the
            // compact path's composed type inside the iOS 1MB main-stack budget
            // during runtime metadata instantiation.
            AnyView(contentWithOptionalModeRail)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                // Title the list root so it isn't a blank bar and the pushed
                // reader's Back button names the section it returns to (#2810).
                .navigationTitle(toolbarTitle)
                #if !os(macOS)
                .navigationBarTitleDisplayMode(.inline)
                #endif
                // One typed destination for every pushed screen (#6944): destinations declared per screen on one
                // view present at the same depth and replace each other.
                .navigationDestination(for: CompactStep.self) { step in
                    compactScreen(step)
                }
                .onChange(of: windowState.compactPath.currentFolderId) { _, id in showCompactFolder(id) }
                .onChange(of: browserSelection) { _, _ in syncPushedReaderDocument() }
                .onChange(of: detailDocument) { _, _ in syncPushedReaderDocument() }
                // Back past the item clears the selection so the list returns clean.
                .onChange(of: windowState.compactPath.itemId) { _, newValue in
                    if newValue == nil {
                        pushedReaderDocument = nil
                        detailDocument = nil
                        browserSelection = []
                    }
                }
                // Mount-time sync (#2666): the push above is driven by CHANGE
                // observers only. A selection already in place when this stack
                // (re)mounts — restored from SceneStorage at launch, or retained
                // across a mode switch — left a selected row whose tap changed
                // nothing, so no onChange ever fired and the reader was
                // unreachable. Syncing on appear makes "stack visible ⇒ pushed
                // reader reflects the selection" an invariant, not an event.
                .onAppear { syncPushedReaderDocument() }
        }
    }

    /// The bar buttons that push the steps `from` offers (#6566).
    @ToolbarContentBuilder
    func compactDocumentStepToolbar(from step: CompactDocumentStep) -> some ToolbarContent {
        ToolbarItemGroup(placement: .primaryAction) {
            ForEach(step.next, id: \.self) { target in
                Button(target.title) {
                    switch target {
                    case .reader: windowState.compactPath.push(.reader)
                    case .info: windowState.compactPath.push(.info)
                    case .source: break
                    }
                }
            }
        }
    }

    /// The screen a path step shows. A folder step shows the shared list, re-rooted on that folder
    /// (`ios.nav.folders-push`, #6945).
    @ViewBuilder
    private func compactScreen(_ step: CompactStep) -> some View {
        switch step {
        case .item:
            previewView
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                // `doc.name` for a page is the upload temp filename (#4416).
                .navigationTitle(pushedReaderDocument.map { DocumentTitle.displayName(for: $0) } ?? "")
                #if !os(macOS)
                .navigationBarTitleDisplayMode(.inline)
                #endif
                .toolbar { compactDocumentStepToolbar(from: .source) }
        case .reader: compactStepScreen(.reader)
        case .info: compactStepScreen(.info)
        case .folder:
            AnyView(contentWithOptionalModeRail)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .navigationTitle(toolbarTitle)
                #if !os(macOS)
                .navigationBarTitleDisplayMode(.inline)
                #endif
        }
    }

    /// The Reader and Info screens pushed from the file: the shell's own reading pane and inspector.
    @ViewBuilder
    private func compactStepScreen(_ step: CompactDocumentStep) -> some View {
        Group {
            switch step {
            case .reader: AnyView(widescreenReadingPane())
            case .info: AnyView(inspectorView)
            case .source: EmptyView()
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .navigationTitle(step.title)
        #if !os(macOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .toolbar { compactDocumentStepToolbar(from: step) }
    }

    /// Compact (iPhone) list→detail stack for the inner-sidebar modes
    /// (Research / Workflow / Activity, #3010). Mirrors `compactLibraryReaderStack`:
    /// the mode's list is the `NavigationStack` root and selecting an item pushes
    /// its detail; `Back` (or a nil `selection`) pops to the list. Compact-only —
    /// regular width keeps its existing two-column rail (the caller's `else`).
    /// `selection` binds the mode's own selection store, so setting it to nil pops.
    @ViewBuilder
    func compactInnerModeStack<Item: Hashable, ListContent: View, DetailContent: View>(
        title: String,
        selection: Binding<Item?>,
        @ViewBuilder list: () -> ListContent,
        @ViewBuilder detail: @escaping (Item) -> DetailContent
    ) -> some View {
        NavigationStack {
            list()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .navigationTitle(title)
                #if !os(macOS)
                .navigationBarTitleDisplayMode(.inline)
                #endif
                .navigationDestination(item: selection) { item in
                    detail(item)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        #if !os(macOS)
                        .navigationBarTitleDisplayMode(.inline)
                        #endif
                }
        }
    }
}
