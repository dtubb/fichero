import OSLog
import SwiftUI
import UniformTypeIdentifiers
#if canImport(AppKit)
import AppKit
#endif
#if canImport(PDFKit)
import PDFKit
#endif

let sidebarRowLogger = Logger(subsystem: "app.fichero.fichero", category: "SidebarRow")

func sidebarSelectionFallback(current: String?, tapped: String) -> String? {
    current == tapped ? nil : tapped
}

/// Visibility rule for the trailing hover open-affordance (#2496): only while
/// the pointer is over the row, never during an inline rename (the field owns
/// the trailing space), and only for rows that can actually be opened
/// (rows without a library have nowhere to route).
func sidebarRowShowsOpenAffordance(isHovered: Bool, isRenaming: Bool, hasLibrary: Bool) -> Bool {
    isHovered && !isRenaming && hasLibrary
}

/// Whether a row paints the pointer-is-over wash (#4097).
///
/// Selection SUPPRESSES hover rather than layering under it. Two washes on one
/// row would sum to something neither was designed to be, and the resulting
/// shade would sit close enough to the selected treatment to be mistaken for
/// it — which is the confusion #4371 is separately trying to remove.
///
/// A named rule rather than an inline `&&` because it is the whole behaviour:
/// the fill and the corner radius are house tokens, so this predicate is the
/// only thing about the hover wash that can be wrong.
func sidebarRowShowsHoverWash(isHovered: Bool, isSelected: Bool) -> Bool {
    isHovered && !isSelected
}

/// Whether a restored/persisted sidebar selection still needs to be driven into
/// the view mode (#2548). `selectedItemId` is restored from `@SceneStorage` at
/// launch, but `SidebarView.onChange(of: selectedItemId)` only fires on a
/// *change* — so a restored selection that equals the persisted value never
/// reaches `handleSelection`, leaving `viewMode` at its default. The visibly
/// highlighted row then doesn't match the detail, and clicking that
/// already-selected row is a no-op (native `List(selection:)` sees no change and
/// the tap fallback guards `current == tapped`). Reconcile when a selection
/// exists but hasn't been handled yet.
func sidebarShouldReconcileSelection(selectedId: String?, lastHandled: String?) -> Bool {
    guard let selectedId else { return false }
    return selectedId != lastHandled
}

/// Transferable wrapper for sidebar row drags (#711).
///
/// Two reasons this exists rather than `.draggable(item.id)` directly:
///   1. `visibility(.ownProcess)` keeps the drag invisible to external
///      apps, preserving the #623 fix that prevented Finder from
///      depositing an HTML link artifact when dragging out of the sidebar.
///   2. Advertising a Transferable on the row makes AppKit's NSTableView
///      row-drag (which List uses under the hood) pull THIS payload
///      instead of synthesizing an empty `public.file-url` when it wins
///      the gesture arena over `.onDrag` — the root cause of #711's
///      "Files dropped: [\"\"]" leak when grabbing from icon/text.
///
/// The bridged NSItemProvider responds to `loadObject(ofClass: NSString.self)`
/// in-process, which is what `SidebarItemRow.handleRowDrop` already filters
/// for — so the drop pipeline didn't need migrating.
struct SidebarDragID: Transferable {
    let id: String
    /// Bare document id + context for cross-app exports (#4123). Nil for
    /// non-document rows — those stay in-process-only, as before.
    var documentId: String?
    var libraryId: UUID?
    var name: String = ""
    /// The document's transcript/content for text-editor drops.
    var transcript: String = ""
    /// 0-based PDF page index for PAGE rows (#4123): the export trims the
    /// parent's multi-page PDF to just this page. Nil = export the whole file.
    var pageIndex: Int?

    /// Rows that can export a real file: documents with a source file
    /// (folders and virtual rows can't).
    var exportsFile: Bool { documentId != nil }
    var exportsText: Bool { !transcript.isEmpty }

    init(id: String) {
        self.id = id
    }

    /// Full payload for a document row (#4123): dragging OUT of the app
    /// delivers a real file copy / rich text instead of the internal id.
    init(item: SidebarItem) {
        self.id = item.id
        if case .document(let doc) = item.itemType, doc.docType != .folder {
            self.documentId = doc.id
            self.libraryId = item.libraryId
            self.name = doc.name
            self.transcript = doc.pageContent ?? ""
            // `sequence` is 1-based (see ContentView+ReadingLayout).
            if doc.docType == .page {
                self.pageIndex = max(0, (doc.sequence ?? 1) - 1)
            }
        }
    }

    /// Same payload for a library-grid document (#4121 Export…) — grid cells
    /// hold a `Document` + window library rather than a `SidebarItem`.
    init(document: Document, libraryId: UUID?) {
        self.id = "doc:\(document.id)"
        if document.docType != .folder {
            self.documentId = document.id
            self.libraryId = libraryId
            self.name = document.name
            self.transcript = document.pageContent ?? ""
            if document.docType == .page {
                self.pageIndex = max(0, (document.sequence ?? 1) - 1)
            }
        }
    }

    static var transferRepresentation: some TransferRepresentation {
        // In-process id flavor — the sidebar move pipeline's payload
        // (#623/#711). FIRST, and it must stay first (#4401).
        //
        // It used to be last, so that "external consumers prefer the real
        // representations above instead of a doc:<uuid> clipping". That
        // reasoning does not apply to THIS representation: `.ownProcess`
        // visibility already hides it from every other application, so no
        // external consumer can see it at any position. Ordering therefore only
        // decides what OUR OWN reader gets — and it was deciding wrong.
        //
        // `handleRowDrop` identifies an internal drag positively, by asking each
        // provider for a string (#4401). `loadObject(ofClass: NSString.self)`
        // returns the FIRST representation an NSString can be made from, and the
        // transcript below is also `utf8PlainText`. So for any document with a
        // transcript — `exportsText` is `!transcript.isEmpty`, i.e. every
        // transcribed document, which is the whole Marshall corpus — the reader
        // got the TRANSCRIPT, never found an id, classified the drag
        // `.unreadableInternal`, and refused the move.
        //
        // That failed safe: nothing was duplicated and the refusal was visible.
        // But it meant transcribed documents could not be filed at all, which is
        // the ordinary act of organising a library. Putting the id first makes
        // the in-process read unambiguous while leaving the cross-app export
        // below exactly as it was.
        ProxyRepresentation(exporting: \.id)
            .visibility(.ownProcess)
        // Cross-app, best-first: a real copy of the source file (fetched via
        // the storage HTTP endpoints — the engine may be remote, NEVER a
        // local path), then the transcript as RTF for text editors.
        FileRepresentation(exportedContentType: .data) { item in
            SentTransferredFile(try await Self.exportSourceFile(for: item))
        }
        .exportingCondition { $0.exportsFile }
        .suggestedFileName(\.name)
        DataRepresentation(exportedContentType: .rtf) { item in
            try Self.transcriptRTFData(item.transcript)
        }
        .exportingCondition { $0.exportsText }
        // UTF-8 serves markdown editors; the in-app drop classifier excludes
        // this flavor so it cannot interfere with sidebar moves (#4123/#4124).
        DataRepresentation(exportedContentType: .utf8PlainText) { item in
            Data(item.transcript.utf8)
        }
        .exportingCondition { $0.exportsText }
    }

    /// Transcript → RTF bytes for rich-text pasteboard consumers.
    static func transcriptRTFData(_ transcript: String) throws -> Data {
        let attributed = NSAttributedString(string: transcript)
        return try attributed.data(
            from: NSRange(location: 0, length: attributed.length),
            documentAttributes: [.documentType: NSAttributedString.DocumentType.rtf]
        )
    }

    /// Fetch the document's source bytes through the library's storage
    /// service into a temp file named for Finder (#4123).
    static func exportSourceFile(for item: SidebarDragID) async throws -> URL {
        guard let documentId = item.documentId else {
            throw CocoaError(.fileNoSuchFile)
        }
        let storage = await MainActor.run { () -> StorageService? in
            let library = item.libraryId.flatMap { LibraryManager.shared.getLibrary(id: $0) }
                ?? LibraryManager.shared.globalLibrary
            return library?.storageService
        }
        guard let storage else { throw CocoaError(.fileNoSuchFile) }
        let (tempURL, disposition) = try await storage.fetchSourceFile(documentId)
        // Prefer the server's filename (its extension picks the app that
        // opens the copy); fall back to a sanitized row name — never a
        // transcript-sized string or embedded newlines.
        let fallback = String(
            item.name.replacingOccurrences(of: "\n", with: " ").prefix(64)
        ).trimmingCharacters(in: .whitespaces)
        let filename = Self.filename(fromContentDisposition: disposition)
            ?? (fallback.isEmpty ? tempURL.lastPathComponent : fallback)
        let named = FileManager.default.temporaryDirectory
            .appendingPathComponent("fichero-drag-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: named, withIntermediateDirectories: true)
        let destination = named.appendingPathComponent(filename)
        try FileManager.default.moveItem(at: tempURL, to: destination)
        if let trimmed = Self.singlePagePDF(from: destination, pageIndex: item.pageIndex) {
            return trimmed
        }
        return destination
    }

    /// Page rows export just THEIR page (#4123): the storage endpoint returns
    /// the parent's whole source file, so trim it client-side. Nil (= keep the
    /// full file) unless this is a page row, the file is a real multi-page
    /// PDF, and extraction succeeds — a trim failure must never lose the drag.
    static func singlePagePDF(from url: URL, pageIndex: Int?) -> URL? {
        #if canImport(PDFKit)
        guard let pageIndex,
              let pdf = PDFDocument(url: url),
              pdf.pageCount > 1,
              let page = pdf.page(at: min(pageIndex, pdf.pageCount - 1)) else {
            return nil
        }
        let single = PDFDocument()
        single.insert(page, at: 0)
        let base = url.deletingPathExtension().lastPathComponent
        let pageURL = url.deletingLastPathComponent()
            .appendingPathComponent("\(base) page \(pageIndex + 1).pdf")
        guard single.write(to: pageURL) else { return nil }
        return pageURL
        #else
        return nil
        #endif
    }

    /// Minimal Content-Disposition filename parse: `filename="x.pdf"` /
    /// `filename=x.pdf`. Returns nil when absent or empty.
    static func filename(fromContentDisposition disposition: String?) -> String? {
        guard let disposition else { return nil }
        for part in disposition.split(separator: ";") {
            let trimmed = part.trimmingCharacters(in: .whitespaces)
            guard trimmed.lowercased().hasPrefix("filename=") else { continue }
            var value = String(trimmed.dropFirst("filename=".count))
            value = value.trimmingCharacters(in: CharacterSet(charactersIn: "\""))
            // No path separators from a header into the filesystem.
            value = value.replacingOccurrences(of: "/", with: "-")
            return value.isEmpty ? nil : value
        }
        return nil
    }
}

extension View {
    /// Applies the sidebar drop-target highlight (accent fill + stroke) to
    /// any view. Placed on the OUTER expression of a SidebarItemRow body
    /// branch so it covers the full List row — including the DisclosureGroup
    /// chevron/indent area that `fullWidthLabel` alone can't reach.
    ///
    /// `.overlay` + `.allowsHitTesting(false)` so the wash renders on top of
    /// whatever chrome the sidebar-style List draws, without blocking drops.
    @ViewBuilder
    func sidebarDropHighlight(
        _ active: Bool, stronger: Bool, operation: SidebarDropOperation = .move
    ) -> some View {
        // Modifier-drag tint — the closest native stand-in for AppKit's
        // drag-cursor badges, which SwiftUI's row drag doesn't expose (no
        // sourceOperationMask hook): ⌥ copy = green, ⌘⌥ alias = purple.
        let tint: Color = switch operation {
        case .move: Color.accentColor
        case .copy: Color.green
        case .alias: Color.purple
        }
        self.overlay(
            RoundedRectangle(cornerRadius: SidebarConstants.cornerRadius)
                .fill(
                    active
                        ? tint.opacity(stronger ? 0.45 : 0.25)
                        : Color.clear
                )
                .overlay(
                    RoundedRectangle(cornerRadius: SidebarConstants.cornerRadius)
                        .stroke(
                            active ? tint : Color.clear,
                            lineWidth: active ? 2 : 0
                        )
                )
                .allowsHitTesting(false)
        )
    }
}

struct SidebarItemRow: View {
    let item: SidebarItem
    let allCachedItems: [SidebarItem]
    @Binding var expandedItems: Set<String>
    @Binding var selectedItemId: String?
    let selectedDestinations: Set<SidebarDestination>
    @Bindable var renameState: RenameStateManager
    @Bindable var deleteState: DeleteStateManager
    @Bindable var sidebarState: SidebarState
    @Bindable var libraryManager: LibraryManager
    var onOpenChatWithCurrentScope: (() -> Void)?

    @Environment(WorkflowExecutionObserver.self) var executionObserver
    /// Finder-style Open in New Tab / New Window for sidebar rows (#1685).
    @Environment(\.openWindow) private var openWindow
    @Environment(\.horizontalSizeClass) var horizontalSizeClass

    var library: LibraryManager.LibraryReference? {
        guard let libraryId = item.libraryId else { return nil }
        return libraryManager.getLibrary(id: libraryId)
    }

    var documentStore: DocumentStore? { library?.documentStore }
    var savedSearchService: SavedSearchService? { library?.savedSearchService }
    var conversationService: ConversationService? { library?.conversationService }
    var workflowStore: WorkflowStore? { library?.workflowStore }
    var chainService: ChainService? { library?.chainService }
    var automationService: AutomationAPIService? { library?.automationService }
    var importService: ImportService? { library?.importService }

    @State var isDropTargeted = false
    /// Pointer-over state driving the trailing open affordance (#2496).
    @State var isRowHovered = false
    /// ⌥/⌘ held while this row is a drop target → copy/alias highlight tint.
    /// Tracked by a flagsChanged monitor installed ONLY while targeted
    /// (macOS; one row is targeted at a time so at most one monitor lives).
    @State var isOptionHeldOverTarget = false
    @State var isCommandHeldOverTarget = false
    #if os(macOS)
    @State private var optionMonitor: Any?
    #endif
    @State var workflowRunProviderCache = WorkflowRunProviderCache.shared
    /// Grid-menu parity (#4121): Bookmark… / Add to Workspace… picker sheets,
    /// presented from this row so each row injects ITS library's services.
    @State var workspacePickerDocument: Document?
    @State var bookmarkPickerDocument: Document?
    @FocusState var isRenameFocused: Bool
    @State var isCommittingRename = false
    @State var isPulsing = false

    var onAutomationPause: (() -> Void)?
    var onAutomationResume: (() -> Void)?
    var onAutomationTrigger: (() -> Void)?
    var onAutomationCancel: (() -> Void)?

    var isFolder: Bool {
        guard case .document(let doc) = item.itemType else { return false }
        return doc.docType == .folder
    }

    /// Inbox is a protected root-level folder (like Finder's "Downloads"
    /// or Mail's "Inbox") — always at the top, never a drag source.
    /// Matches the `buildInboxItem` builder in `SidebarItemBuilder` that
    /// stamps the "tray.fill" icon onto the library's Inbox doc.
    var isInboxFolder: Bool {
        item.icon == "tray.fill"
    }

    /// The workflow id whose run-state this row should display, or nil for
    /// non-workflow rows. Mirror DOC rows share their workflow's id (the
    /// engine mirrors workflows into same-id document nodes), so the sidebar
    /// spinner survives #4186's removal of the virtual workflow rows.
    /// Static + pure for testability (nonisolated: statics on View types
    /// inherit MainActor under the macOS 26 SDK and tests run off-main).
    nonisolated static func runStateWorkflowId(for item: SidebarItem) -> String? {
        switch item.itemType {
        case .workflow(let workflow):
            return workflow.id
        case .document(let doc) where doc.isWorkflowNode:
            return doc.id
        default:
            return nil
        }
    }

    var workflowIsRunning: Bool {
        guard let workflowId = Self.runStateWorkflowId(for: item) else { return false }
        return executionObserver.isRunning(workflowId: workflowId)
    }

    /// True when this sidebar row's document is currently being processed
    /// by a workflow, OR (for folders) any of its direct children is. Drives
    /// a sidebar spinner so users can see processing activity even when the
    /// item isn't visible in the grid. (#785)
    ///
    /// Reads `Document.status` from the live `DocumentStore` rather than the
    /// captured `SidebarItem.itemType` snapshot — the store is what the
    /// workflow stream mutates via `updateProcessingStatus(forPath:status:)`.
    /// What this row should indicate, separating work ON this document from
    /// work on its CONTENTS (#4417).
    ///
    /// The aggregation is unchanged from #4295 — the same sources, the same
    /// tolerance for stale container copies. What changed is that a busy child
    /// no longer collapses into the parent's own spinner.
    var containerActivity: ContainerActivity {
        guard case .document(let doc) = item.itemType, let store = documentStore else {
            return .idle
        }
        // #4295: busy is derived from the RUNNING EXECUTION'S TARGETS
        // (status overrides + every live container, including the sidebar's
        // childrenCache), never from selection-scoped state — the old lookup
        // stopped at currentDocuments/collections, so a page row's spinner
        // only rendered while its parent was the selected collection.
        let isSelfProcessing = store.isDocumentBusy(doc.id) || doc.status == .processing

        // Any container aggregates, not only folders: the reported case was a
        // PDF spinning alongside its four page children.
        let counts = store.childActivityCounts(of: doc.id)

        return ContainerActivity.resolve(
            isSelfProcessing: isSelfProcessing,
            busyChildren: counts.busy,
            totalChildren: counts.total
        )
    }

    /// The per-item spinner, now only for a document that is itself the
    /// subject of work. A container with busy children shows the aggregate.
    var documentIsProcessing: Bool {
        containerActivity.showsLeafSpinner
    }

    var workflowProgress: Double? {
        guard let workflowId = Self.runStateWorkflowId(for: item) else { return nil }
        return executionObserver.getProgress(for: workflowId)
    }

    var isExpanded: Binding<Bool> {
        Binding(
            get: { expandedItems.contains(item.id) },
            set: { isExpanded in
                if isExpanded {
                    expandedItems.insert(item.id)
                    guard case .document(let document) = item.itemType,
                          let store = documentStore else { return }
                    // NOTE: the old guard required a positive child count and
                    // was dead — not because the backend omits `child_count`
                    // (it does not; that premise was wrong, #4515) but because
                    // the client's converter dropped the typed field, so every
                    // folder decoded 0. Children then loaded only as a
                    // side-effect of SELECTING the folder — the #3355 root
                    // cause. Load whenever they aren't cached yet: the count
                    // is now honest, and re-adding the guard would still be
                    // wrong for a folder whose count arrived after expansion.
                    #if canImport(AppKit)
                    let optionHeld = NSApp.currentEvent?.modifierFlags.contains(.option) ?? false
                    #else
                    let optionHeld = false
                    #endif
                    if optionHeld {
                        // Option-click: expand the WHOLE subtree, Finder-style.
                        Task { await expandSubtree(document, store: store) }
                    } else {
                        // #4293: ALWAYS run the one-level load+prefetch on
                        // expand. The old guard skipped it when this row's
                        // children were already cached (e.g. by the root-level
                        // prefetch in loadCollections) — but loadSidebarChildren
                        // is ALSO what prefetches the grandchildren, so a
                        // prefetched folder's SUBfolders (workflow folders
                        // under "Default Workflows", a folder of folders two
                        // levels down) never got children cached, rendered
                        // chevron-less, and could not be expanded at all.
                        // Idempotent + cheap when everything is cached:
                        // cacheSidebarChildren returns the cache hit and
                        // containersNeedingChildren comes back empty.
                        Task { await store.loadSidebarChildren(of: document) }
                    }
                } else {
                    expandedItems.remove(item.id)
                }
            }
        )
    }

    /// Option-click expands the ENTIRE subtree (Finder), lazily loading each
    /// level. An explicit user gesture, so the deep fan-out fetch is acceptable
    /// — unlike the bounded one-level prefetch in `loadSidebarChildren`.
    @MainActor
    func expandSubtree(_ document: Document, store: DocumentStore) async {
        expandedItems.insert("doc:\(document.id)")
        let children = await store.cacheSidebarChildren(of: document)
        for child in children where child.docType == .folder {
            await expandSubtree(child, store: store)
        }
    }

    /// Widens `itemLabel`'s hit region to the full available width so
    /// drops fire when the cursor is anywhere over the row, not just on
    /// the icon+text. Tight vertical padding to match Xcode's dense
    /// sidebar rhythm (~18pt row height).
    ///
    /// No `.draggable` here — that lives on the outer row container in
    /// the `ForEach`. A `.draggable` placed inside a `DisclosureGroup`
    /// label's `NSHostingView` creates a side-channel drag session that
    /// bypasses NSTableView's row-drag mechanism, producing a small
    /// label-only preview and silently skipping `.dropDestination` on
    /// the ForEach (#711).
    var fullWidthLabel: some View {
        itemLabel
            .padding(.vertical, 1)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            // Hover wash (#4097). #2496's real cause was not that rows are hard
            // to HIT but that they are hard to AIM at: nothing told you what the
            // pointer was over until selection had already happened. The trailing
            // open-affordance added for #2496 is a hover cue at the row's far
            // edge; this is the one under the pointer.
            //
            // `.background`, not `.overlay`, so it can never dim the label.
            // Suppressed while selected so the two never stack — and it is
            // `LibrarySelectionStyle.fill` at half opacity, so hover cannot
            // read as selection by construction rather than by two hand-tuned
            // values someone must keep in the right order.
            //
            // Every Frame Perfect: this changes a fill only. No metrics move
            // between hovered and not, so hovering cannot relayout or
            // re-truncate the row name — the same discipline the trailing
            // affordance follows by staying in the layout and toggling opacity.
            .background(
                RoundedRectangle(cornerRadius: SidebarConstants.cornerRadius)
                    .fill(
                        sidebarRowShowsHoverWash(isHovered: isRowHovered, isSelected: isRowSelected)
                            ? LibrarySelectionStyle.hoverFill
                            : Color.clear
                    )
                    .allowsHitTesting(false)
            )
            // Full name on hover — row names truncate (`lineLimit(1)`) with no
            // other way to reveal themselves. Empty string disables the tooltip
            // during inline rename (same idiom as the read-only library help).
            // The trailing affordance's own `.help` wins over its frame.
            .help(renameState.renamingItemId == item.id ? "" : item.name)
            #if os(macOS)
            .onHover { isRowHovered = $0 }
            #endif
    }

    /// Document id when this sidebar row represents a document or folder —
    /// used to focus it after opening in a new tab/window (#1685).
    var openableDocumentId: String? {
        if case .document(let doc) = item.itemType { return doc.id }
        return nil
    }

    #if os(macOS)
    /// Track ⌥ while this row is targeted so the highlight can tint to copy
    /// mode live. Note: whether flagsChanged reaches a local monitor during
    /// an active drag session needs a gate eyeball; the drop BEHAVIOR reads
    /// the key again at drop time regardless (`sidebarOptionKeyIsHeld`).
    func updateOptionMonitor(targeted: Bool) {
        if targeted {
            isOptionHeldOverTarget = NSEvent.modifierFlags.contains(.option)
            isCommandHeldOverTarget = NSEvent.modifierFlags.contains(.command)
            guard optionMonitor == nil else { return }
            optionMonitor = NSEvent.addLocalMonitorForEvents(matching: .flagsChanged) { event in
                isOptionHeldOverTarget = event.modifierFlags.contains(.option)
                isCommandHeldOverTarget = event.modifierFlags.contains(.command)
                return event
            }
        } else {
            if let optionMonitor {
                NSEvent.removeMonitor(optionMonitor)
            }
            optionMonitor = nil
            isOptionHeldOverTarget = false
            isCommandHeldOverTarget = false
        }
    }
    #endif

    /// The operation the CURRENT modifiers would perform on this drop target —
    /// drives the highlight tint only; the drop re-reads the keys itself.
    var targetedDropOperation: SidebarDropOperation {
        sidebarDropOperation(
            optionHeld: isOptionHeldOverTarget,
            commandHeld: isCommandHeldOverTarget,
            kind: .document
        )
    }

    /// In-window "Open": select this row (drives navigation/preview).
    func openInWindow() {
        selectedItemId = item.id
    }

    /// "Open in New Tab / New Window": open a fresh window on this item's
    /// library via the shared Safari new-window path. For document/folder rows
    /// the document is focused once the new window loads; other item types open
    /// the library and leave deeper focus as a follow-up.
    func openInNewWindow(asTab: Bool) {
        // Follow-up (#1685): focus non-document sidebar items (saved
        // searches, workflows, chats) in the new window — needs a pending
        // sidebar selection consumed by SidebarView, mirroring
        // pendingOpenDocumentId.
        guard let libraryId = item.libraryId ?? libraryManager.currentLibraryId else { return }
        WindowOpener.open(
            libraryId: libraryId,
            documentId: openableDocumentId,
            asTab: asTab,
            using: openWindow
        )
    }

}
