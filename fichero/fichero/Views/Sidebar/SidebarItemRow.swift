// swiftlint:disable file_length
import OSLog
import SwiftUI
import UniformTypeIdentifiers

let sidebarRowLogger = Logger(subsystem: "com.fichero.fichero", category: "SidebarRow")

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
    static var transferRepresentation: some TransferRepresentation {
        ProxyRepresentation(exporting: \.id)
            .visibility(.ownProcess)
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
    func sidebarDropHighlight(_ active: Bool, stronger: Bool) -> some View {
        self.overlay(
            RoundedRectangle(cornerRadius: SidebarConstants.cornerRadius)
                .fill(
                    active
                        ? Color.accentColor.opacity(stronger ? 0.45 : 0.25)
                        : Color.clear
                )
                .overlay(
                    RoundedRectangle(cornerRadius: SidebarConstants.cornerRadius)
                        .stroke(
                            active ? Color.accentColor : Color.clear,
                            lineWidth: active ? 2 : 0
                        )
                )
                .allowsHitTesting(false)
        )
    }
}

// swiftlint:disable:next type_body_length
struct SidebarItemRow: View {
    let item: SidebarItem
    let allCachedItems: [SidebarItem]
    @Binding var expandedItems: Set<String>
    @Binding var selectedItemId: String?
    @ObservedObject var renameState: RenameStateManager
    @ObservedObject var deleteState: DeleteStateManager
    @ObservedObject var libraryManager: LibraryManager

    @Environment(WorkflowExecutionObserver.self) var executionObserver

    var library: LibraryManager.LibraryReference? {
        guard let libraryId = item.libraryId else { return nil }
        return libraryManager.getLibrary(id: libraryId)
    }

    var documentStore: DocumentStore? { library?.documentStore }
    var savedSearchService: SavedSearchServiceGenerated? { library?.savedSearchServiceGenerated }
    var conversationService: ConversationServiceGenerated? { library?.conversationServiceGenerated }
    var workflowStore: WorkflowStore? { library?.workflowStore }
    var chainService: ChainService? { library?.chainService }
    var automationService: AutomationServiceGenerated? { library?.automationService }
    var importService: ImportServiceGenerated? { library?.importService }

    @State var isDropTargeted = false
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

    var workflowIsRunning: Bool {
        guard case .workflow(let workflow) = item.itemType else { return false }
        return executionObserver.isRunning(workflowId: workflow.id)
    }

    /// True when this sidebar row's document is currently being processed
    /// by a workflow, OR (for folders) any of its direct children is. Drives
    /// a sidebar spinner so users can see processing activity even when the
    /// item isn't visible in the grid. (#785)
    ///
    /// Reads `Document.status` from the live `DocumentStore` rather than the
    /// captured `SidebarItem.itemType` snapshot — the store is what the
    /// workflow stream mutates via `updateProcessingStatus(forPath:status:)`.
    var documentIsProcessing: Bool {
        guard case .document(let doc) = item.itemType, let store = documentStore else {
            return false
        }
        let live = store.currentDocuments.first(where: { $0.id == doc.id })
            ?? store.collections.first(where: { $0.id == doc.id })
            ?? doc
        if live.status == .processing { return true }
        // Folder: also report processing if any direct child is. We read
        // from childrenCache to avoid a fetch — if the cache isn't populated
        // yet, the folder won't show a spinner until the user expands it,
        // which is acceptable.
        if doc.docType == .folder, let kids = store.childrenCache[doc.id] {
            return kids.contains { $0.status == .processing }
        }
        return false
    }

    var workflowProgress: Double? {
        guard case .workflow(let workflow) = item.itemType else { return nil }
        return executionObserver.getProgress(for: workflow.id)
    }

    private var isExpanded: Binding<Bool> {
        Binding(
            get: { expandedItems.contains(item.id) },
            set: { isExpanded in
                if isExpanded {
                    expandedItems.insert(item.id)
                } else {
                    expandedItems.remove(item.id)
                }
            }
        )
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
    private var fullWidthLabel: some View {
        itemLabel
            .padding(.vertical, 1)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
    }

    private var rowContextMenu: some View {
        Group {
            SidebarItemContextMenu(
                item: item,
                renameState: renameState,
                deleteState: deleteState,
                onPause: onAutomationPause,
                onResume: onAutomationResume,
                onTrigger: onAutomationTrigger,
                onCancel: onAutomationCancel
            )

            if case .document(let doc) = item.itemType,
               let workflows = workflowStore?.workflows, !workflows.isEmpty {
                Divider()
                Menu("Run Workflow") {
                    workflowMenuItems(workflows: workflows) { workflowId in
                        runWorkflowOnDocument(workflowId: workflowId, docId: doc.id)
                    }
                }
            }
        }
    }

    /// Builds a `Run Workflow` submenu where workflows whose `folderPath`
    /// is "/" appear at the top level and workflows under any other folder
    /// path are grouped into a `Menu("<folder>")` submenu (#722). Folder
    /// paths like `/Transcribe` and `/Catalogue` give us nested
    /// submenus matching the user's mental model. Workflows are sorted
    /// alphabetically within each group; folder names are sorted
    /// alphabetically too.
    @ViewBuilder
    private func workflowMenuItems(
        workflows: [WorkflowSidebarItem],
        action: @escaping (String) -> Void
    ) -> some View {
        let grouped = Dictionary(grouping: workflows) { wf in
            wf.folderPath.isEmpty ? "/" : wf.folderPath
        }
        let topLevel = (grouped["/"] ?? []).sorted { $0.name < $1.name }
        let folderKeys = grouped.keys
            .filter { $0 != "/" }
            .sorted()

        ForEach(topLevel) { workflow in
            Button(workflow.name) { action(workflow.id) }
        }

        ForEach(folderKeys, id: \.self) { folderPath in
            Menu(folderLabel(for: folderPath)) {
                let inFolder = (grouped[folderPath] ?? []).sorted { $0.name < $1.name }
                ForEach(inFolder) { workflow in
                    Button(workflow.name) { action(workflow.id) }
                }
            }
        }
    }

    /// "/Transcribe" → "Transcribe"; "/Catalogue/Sub" → "Sub" (last
    /// component, mirroring how Finder shows nested folders in menus).
    private func folderLabel(for path: String) -> String {
        let trimmed = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        if trimmed.isEmpty { return path }
        return String(trimmed.split(separator: "/").last ?? Substring(trimmed))
    }

    /// Run a workflow on this sidebar document via the same SSE path that
    /// ContentView's toolbar/menubar/grid-context-menu use. Previously this
    /// went through BatchService.createBatch + executeBatch, which produced
    /// an executing run that the Activity view didn't register (BatchService
    /// path doesn't notify executionObserver), so users reported "context
    /// menu Run Workflow doesn't work" while the toolbar one did. Converging
    /// on the SSE path is #694's fix.
    private func runWorkflowOnDocument(workflowId: String, docId: String) { // swiftlint:disable:this function_body_length
        guard let library = library else {
            sidebarRowLogger.error("runWorkflowOnDocument: no library reference")
            return
        }
        let workflowName = workflowStore?.workflows
            .first(where: { $0.id == workflowId })?.name ?? workflowId
        let stream = library.workflowStreamService
        let observer = executionObserver
        Task { @MainActor in
            var streamCompleted = false
            do {
                let store = library.documentStore
                let response = try await stream.execute(
                    workflowId: workflowId,
                    inputs: ["selected_doc_ids": [docId]],
                    onEvent: { event in
                        observer.handleEvent(event, for: workflowId)
                        // Per-doc spinner: mirror SSE file events to
                        // Document.status so grid icons + sidebar folders
                        // show processing state. Sidebar context-menu was
                        // the 4th workflow run path missing this wire-up
                        // (alongside ContentView+Actions, WorkflowEditor,
                        // and LibraryView+FilterAndBatch). #785
                        switch event {
                        case .fileStart(_, _, let filePath, _, _, _):
                            store.updateProcessingStatus(forPath: filePath, status: .processing)
                        case .fileComplete(_, _, let filePath, _, _, _, _):
                            store.updateProcessingStatus(forPath: filePath, status: .completed)
                        case .fileError(_, _, let filePath, _, _):
                            store.updateProcessingStatus(forPath: filePath, status: .failed)
                        default:
                            break
                        }
                        switch event {
                        case .complete, .error, .systemicError:
                            streamCompleted = true
                        default:
                            break
                        }
                    }
                )
                let threadId = response.threadId
                observer.startExecution(
                    workflowId: workflowId,
                    name: workflowName,
                    threadId: threadId,
                    onCancel: { [weak stream] in
                        Task { @MainActor in
                            try? await stream?.stopWorkflow(threadId: threadId)
                        }
                    }
                )
                while !streamCompleted {
                    try await Task.sleep(for: .milliseconds(200))
                    if Task.isCancelled { break }
                    if let exec = observer.activeExecutions[workflowId], !exec.isRunning {
                        streamCompleted = true
                    }
                }
                let status: WorkflowStatus = {
                    guard let exec = observer.activeExecutions[workflowId] else { return .completed }
                    return exec.workflowError != nil || exec.status == .failed ? .failed : .completed
                }()
                observer.endExecution(workflowId: workflowId, status: status)
            } catch {
                sidebarRowLogger.error("Sidebar Run Workflow failed: \(error)")
                observer.endExecution(workflowId: workflowId, status: .failed)
            }
        }
    }

    var body: some View {
        bodyContent
            // DisclosureGroup label and the row drag both watch mouse-down
            // and compete with List(selection:) for the tap event, causing
            // intermittent click failures on icon/text (#645). A
            // simultaneousGesture forces the selection binding to update
            // regardless of which other handler wins the gesture arena.
            .simultaneousGesture(TapGesture().onEnded {
                selectedItemId = item.id
            })
            // SwiftUI `Text` registers itself as an NSDraggingSource for
            // selectable text on macOS. That AppKit-level drag source
            // wins over the row container's `.draggable`, producing a
            // text-only drag (icon+name preview, not the full row, and
            // bypassing our SidebarDragID Transferable so drops don't
            // fire). Disabling text selection takes Text out of the
            // drag arena so the row's `.draggable` is the sole drag
            // source (#711).
            .textSelection(.disabled)
            .accessibilityLabel(accessibilityLabel)
            .accessibilityHint(accessibilityHint)
            .accessibilityValue(accessibilityValue)
    }

    /// VoiceOver label — the row's displayed name plus its kind so users
    /// who navigate the sidebar non-visually can tell sections apart.
    /// Sidebar plan Step 10 (#584).
    private var accessibilityLabel: String {
        switch item.itemType {
        case .document(let doc):
            return doc.docType == .folder
                ? "\(item.name), folder"
                : "\(item.name), \(doc.fileType?.rawValue ?? "file")"
        case .savedSearch: return "\(item.name), saved search"
        case .conversation: return "\(item.name), conversation"
        case .workflow: return "\(item.name), workflow"
        case .chain: return "\(item.name), workflow chain"
        case .schedule: return "\(item.name), schedule"
        case .trigger: return "\(item.name), trigger"
        case .folder: return "\(item.name), \(item.category.rawValue) folder"
        case .libraryHeader: return "\(item.name), library"
        case .batch, .comparison, .activityRun:
            return item.name
        }
    }

    /// Available actions callable via the context menu. Kept terse so
    /// VoiceOver users don't hear a long recitation each time they land
    /// on a row; power actions like export/duplicate stay discoverable
    /// via `.accessibilityAction` on the context menu itself.
    private var accessibilityHint: String {
        if item.itemType.canBeRenamed {
            return "Double-click to rename. Drag to reorder or move to a folder. Right-click for more actions."
        }
        return "Right-click for actions."
    }

    /// Expansion state for folder rows — read as "expanded"/"collapsed"
    /// so arrow-key navigation via VoiceOver correctly reflects the
    /// DisclosureGroup state.
    private var accessibilityValue: String {
        guard isExpandable else { return "" }
        return expandedItems.contains(item.id) ? "expanded" : "collapsed"
    }

    private var isExpandable: Bool {
        guard let children = item.children else { return false }
        return !children.isEmpty
    }

    // Folders (with or without children) are drop targets; leaves
    // (PDFs, images, saved searches, etc.) are drag sources only.
    // Matches Finder semantics: you can drag a file out, but you
    // can't drop anything onto a file.
    @ViewBuilder
    private var bodyContent: some View {
        if let children = item.children, !children.isEmpty {
            DisclosureGroup(isExpanded: isExpanded) {
                childrenList(children)
            } label: {
                folderLabel
            }
        } else if isFolder {
            folderLabel
        } else {
            leafLabel
        }
    }

    /// Folder row: drop target always; drag source EXCEPT for the
    /// protected Inbox folder (#621). Inbox stays anchored at the top;
    /// users can drag files INTO it but not drag Inbox itself to
    /// another position or parent.
    ///
    /// `.utf8PlainText` handles internal sidebar drags; `.item` is the
    /// root UTType conforming to every file / folder type so Finder
    /// drops match without enumerating each concrete UTI.
    @ViewBuilder
    private var folderLabel: some View {
        fullWidthLabel
            .sidebarDropHighlight(isDropTargeted, stronger: true)
            .onDrop(
                of: [UTType.utf8PlainText, UTType.item],
                isTargeted: $isDropTargeted
            ) { providers in
                handleRowDrop(providers)
            }
            .contextMenu { rowContextMenu }
    }

    /// Leaf row: no inner gestures — `.draggable` is applied one level
    /// up at the row container so clicks on icon/text aren't delayed by
    /// SwiftUI's tap-vs-drag disambiguation (#711 follow-up).
    private var leafLabel: some View {
        fullWidthLabel
            .contextMenu { rowContextMenu }
    }

    /// Optimistic accept: any provider that can produce a URL or String
    /// returns true immediately; async loading continues in background.
    /// Synchronous `canLoadObject` pre-filtering misses URL-producing
    /// items because macOS advertises some capabilities asynchronously.
    private func handleRowDrop(_ providers: [NSItemProvider]) -> Bool {
        #if DEBUG
        sidebarRowLogger.debug("📥 handleRowDrop fired on \(item.name) with \(providers.count) provider(s)")
        for (idx, provider) in providers.enumerated() {
            let utis = provider.registeredTypeIdentifiers.joined(separator: ", ")
            let canURL = provider.canLoadObject(ofClass: URL.self)
            let canString = provider.canLoadObject(ofClass: NSString.self)
            sidebarRowLogger.debug("  [\(idx)] UTIs: [\(utis)]  URL:\(canURL)  String:\(canString)")
        }
        #endif

        guard !providers.isEmpty else { return false }

        // Providers that can ONLY load String (not URL) are internal
        // sidebar drags — `.draggable(item.id)` advertises the String via
        // utf8PlainText. Route them through the sidebar-internal path.
        let textOnly = providers.filter {
            !$0.canLoadObject(ofClass: URL.self) && $0.canLoadObject(ofClass: NSString.self)
        }

        if !textOnly.isEmpty {
            Task {
                var ids: [String] = []
                for provider in textOnly {
                    if let str = try? await Self.loadString(from: provider) {
                        ids.append(str)
                    }
                }
                guard !ids.isEmpty else { return }
                _ = handleDropIntoFolder(itemIDs: ids, targetFolder: item)
            }
            return true
        }

        // Anything else — Finder drags with URL or content UTIs — goes
        // through the optimistic Finder-import path.
        _ = handleProvidersDrop(providers, targetFolder: item)
        return true
    }

    /// Async helper to unwrap a plain-text NSItemProvider into a String.
    /// Matches the `loadURL` helper's pattern on `SidebarItemRow+DropHandlers`.
    private static func loadString(from provider: NSItemProvider) async throws -> String {
        try await withCheckedThrowingContinuation { continuation in
            _ = provider.loadObject(ofClass: NSString.self) { value, error in
                if let error {
                    continuation.resume(throwing: error)
                } else if let nsString = value as? NSString {
                    continuation.resume(returning: nsString as String)
                } else {
                    continuation.resume(throwing: NSError(domain: "SidebarRowDrop", code: -1))
                }
            }
        }
    }

    @ViewBuilder
    private func childrenList(_ children: [SidebarItem]) -> some View {
        // Cross-hierarchy / cross-section drops use SwiftUI's native
        // `.dropDestination(for:action:)` on the ForEach (DynamicViewContent)
        // which exposes the insertion offset — the same `.above`-targeting
        // capability NSTableView has, just one level up. Same-section
        // reorder via the row's native drag handle still goes through
        // `.onMove` and shows the system's row-drop indicator.
        ForEach(Array(children.enumerated()), id: \.element.id) { _, child in
            SidebarItemRow(
                item: child,
                allCachedItems: allCachedItems,
                expandedItems: $expandedItems,
                selectedItemId: $selectedItemId,
                renameState: renameState,
                deleteState: deleteState,
                libraryManager: libraryManager
            )
            .contentShape(Rectangle())
            // `.draggable` BEFORE `.tag` so NSTableView's row-drag
            // mechanism arms the Transferable at the row level before
            // the row identity is bound. Apple's ArticleCollectionView
            // sample puts `.draggable` directly on the leaf cell view
            // with no intervening `.tag` — order matters here.
            .draggable(child.icon == "tray.fill" ? SidebarDragID(id: "") : SidebarDragID(id: child.id))
            .moveDisabled(child.icon == "tray.fill")
            .tag(child.id)
        }
        .dropDestination(for: SidebarDragID.self) { ids, offset in
            sidebarRowLogger.debug("🎯 nested .dropDestination FIRED with \(ids.count) ids at offset \(offset)")
            handleNestedInsertionDrop(
                droppedIds: ids.map(\.id),
                at: offset,
                into: children
            )
        }
        .onMove { source, destination in
            if source.contains(where: { children[$0].icon == "tray.fill" }) {
                return
            }
            guard let store = documentStore,
                  let orderedIds = sidebarReorderedDocIds(
                      children: children,
                      moving: source,
                      to: destination
                  ) else { return }
            store.reorderChildrenOptimistically(orderedIds: orderedIds)
        }
    }

    /// Cross-hierarchy insert into THIS folder's children at `offset`.
    /// Cycle-prevented: any dropped item that is an ancestor of this
    /// folder is silently skipped (can't make a folder a child of its
    /// own descendant).
    private func handleNestedInsertionDrop(
        droppedIds: [String],
        at offset: Int,
        into children: [SidebarItem]
    ) {
        guard case .document(let parentDoc) = item.itemType,
              parentDoc.docType == .folder,
              let store = documentStore else {
            return
        }

        let bareIds = droppedIds
            .filter { $0.hasPrefix("doc:") }
            .map { extractActualId(from: $0) }
            .filter { bareId in
                !isDescendant(item.id, of: "doc:\(bareId)")
            }

        guard let newOrder = sidebarReorderedDocIdsWithInsert(
            children: children,
            inserting: bareIds,
            at: offset
        ) else { return }

        Task {
            for bareId in bareIds {
                _ = try? await store.moveDocument(bareId, toParent: parentDoc.id)
            }
            await MainActor.run {
                store.reorderChildrenOptimistically(orderedIds: newOrder)
            }
        }
    }

}

// MARK: - Preview

/// Self-contained visual preview of the sidebar's List + DisclosureGroup
/// + Label stack. No backend, no services, no bindings to real state —
/// just static SwiftUI so we can iterate on fonts, selection highlight,
/// and section-header weight via Xcode Previews (or
/// `mcp__xcode__RenderPreview`).
///
/// Keep this in sync with the styling choices in `LibrarySectionHeader`,
/// `SidebarView+ViewComponents.unifiedDisclosureSection`, and any other
/// rendering-only detail the real sidebar applies.
#Preview("Sidebar look") {
    SidebarVisualPreview()
        .frame(width: 260, height: 500)
}

private struct SidebarVisualPreview: View {
    @State private var selection: String? = "doc-a"
    @State private var librariesExpanded = true
    @State private var searchesExpanded = true

    var body: some View {
        List(selection: $selection) {
            Section {
                DisclosureGroup(isExpanded: $librariesExpanded) {
                    row(id: "doc-a", name: "Inbox", icon: "tray")
                    row(id: "doc-b", name: "Chota Valley", icon: "folder")
                    row(id: "doc-c", name: "Small Text", icon: "folder")
                    row(id: "doc-d", name: "Working", icon: "folder")
                } label: {
                    Text("Library")
                        .font(.caption)
                        .fontWeight(.bold)
                        .foregroundStyle(.primary)
                }
                DisclosureGroup(isExpanded: $searchesExpanded) {
                    row(id: "search-a", name: "New Search", icon: "magnifyingglass")
                    row(id: "search-b", name: "Colombia", icon: "magnifyingglass")
                    row(id: "search-c", name: "belcher", icon: "magnifyingglass")
                } label: {
                    Text("Saved Searches")
                        .font(.caption)
                        .fontWeight(.bold)
                        .foregroundStyle(.primary)
                }
            }
        }
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)
    }

    @ViewBuilder
    private func row(id: String, name: String, icon: String) -> some View {
        Label(name, systemImage: icon)
            .tag(id)
    }
}
