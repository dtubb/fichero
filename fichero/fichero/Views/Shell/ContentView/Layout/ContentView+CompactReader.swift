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
        guard let doc = candidate, doc.docType != .folder else { return nil }
        return doc
    }

    private func compactReaderLeaf() -> Document? {
        Self.resolveCompactReaderLeaf(
            detailDocument: detailDocument,
            selectedId: browserSelection.first,
            // The SAME array LibraryView is showing: transient-search hits can
            // live outside the browsed folder, so resolving only from
            // `currentDocuments` left search-result taps unresolvable (#2666).
            displayedDocuments: activeSearchQuery == nil
                ? selectedDocuments
                : searchResultDocuments,
            fallbackDocuments: documentStore.currentDocuments
        )
    }

    /// Push the resolved leaf into `pushedReaderDocument` (#2666). Writing real
    /// @State — instead of feeding `.navigationDestination(item:)` a computed
    /// Binding — is what makes the push fire reliably on selection change.
    private func syncPushedReaderDocument() {
        let leaf = compactReaderLeaf()
        if pushedReaderDocument?.id != leaf?.id {
            pushedReaderDocument = leaf
        }
    }

    /// Compact (iPhone) library/search reader stack (#2551). The list is the
    /// root; selecting a leaf document pushes the reader — the SAME `previewView`
    /// EditorView the regular content pane shows in its preview slot, so there is
    /// no parallel reader. `NavigationStack` supplies the Back affordance.
    /// Internal (not private): referenced from ContentView+SidebarLayout.swift's
    /// `centerContentRouting` — `private` is file-scoped.
    @ViewBuilder
    var compactLibraryReaderStack: some View {
        NavigationStack {
            // AnyView is load-bearing (#4331): this iPhone-only stack sits at the
            // deepest point of the shell's getter chain — erasing here keeps the
            // compact path's composed type inside the iOS 1MB main-stack budget
            // during runtime metadata instantiation.
            AnyView(contentWithOptionalModeRail)
                .overlay { paneFocusIndicator(for: .content) }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                // Title the list root so it isn't a blank bar and the pushed
                // reader's Back button names the section it returns to (#2810).
                .navigationTitle(toolbarTitle)
                #if !os(macOS)
                .navigationBarTitleDisplayMode(.inline)
                #endif
                // Drive the push from real @State (#2666). Selection changes
                // recompute the leaf; popping (Back / back-swipe) sets the item
                // to nil, which clears the selection so the list returns clean.
                .navigationDestination(item: $pushedReaderDocument) { doc in
                    previewView
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        // The pushed reader is the "reader tab" #4416 named:
                        // `doc.name` for a page is the upload temp filename.
                        .navigationTitle(DocumentTitle.displayName(for: doc))
                        #if !os(macOS)
                        // A pushed reader is a detail screen: keep the title bar
                        // compact (inline) rather than the default large title.
                        .navigationBarTitleDisplayMode(.inline)
                        #endif
                        // ponytail: full edge-swipe paging between pipeline stages
                        // is deferred. Back (NavigationStack) returns to the list,
                        // and EditorView already hosts SwipeSiblingNavigator for
                        // two/three-finger sibling paging. Add explicit
                        // stage-to-stage swiping later if wanted. (#2551)
                }
                .onChange(of: browserSelection) { _, _ in syncPushedReaderDocument() }
                .onChange(of: detailDocument) { _, _ in syncPushedReaderDocument() }
                .onChange(of: pushedReaderDocument) { _, newValue in
                    if newValue == nil {
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
