import AppKit
import OSLog
import SwiftUI
import UniformTypeIdentifiers

// swiftlint:disable file_length

// MARK: - View Components

extension SidebarView {
    private struct UnifiedLibraryBuckets {
        let documentItems: [SidebarItem]
        let searchItems: [SidebarItem]
        let workflowItems: [SidebarItem]
        let chainItems: [SidebarItem]
        let scheduleItems: [SidebarItem]
        let triggerItems: [SidebarItem]
        let activityItems: [SidebarItem]
    }

    @ViewBuilder
    var sidebarContent: some View {
        VStack(spacing: 0) {
            unifiedContent

            // Bottom toolbar
            if shouldShowBottomToolbar {
                Divider()
                SidebarBottomToolbar(
                    createSearch: createNewSearch,
                    createChat: createNewChat,
                    createWorkflow: createNewWorkflow,
                    createFolder: handleCreateNewFolder,
                    importFiles: importFiles,
                    createComparison: createNewComparison,
                    createSchedule: createNewSchedule,
                    createTrigger: createNewTrigger
                )
            }
        }
    }

    /// Whether to show the bottom toolbar.
    var shouldShowBottomToolbar: Bool {
        true
    }

    /// Unified sidebar content with feature-gated sections per library.
    @ViewBuilder
    var unifiedContent: some View {
        List(selection: $selectedItemId) {
            ForEach(cachedLibraryHeaders) { libraryHeader in
                unifiedLibrarySection(libraryHeader)
            }
        }
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)
        .onDeleteCommand {
            deleteSelectedActivityRuns()
        }
    }

    @ViewBuilder
    // swiftlint:disable:next function_body_length cyclomatic_complexity
    private func unifiedLibrarySection(_ libraryHeader: SidebarItem) -> some View {
        if let libraryId = libraryHeader.libraryId,
           let library = libraryManager.getLibrary(id: libraryId) {
            let allChildren = libraryHeader.children ?? []
            let documentItems = allChildren.filter { item in
                if case .document = item.itemType { return true }
                if case .folder = item.itemType, item.category == .folder { return true }
                return false
            }
            let searchItems = allChildren.filter { item in
                if case .savedSearch = item.itemType { return true }
                if case .folder = item.itemType, item.category == .search { return true }
                return false
            }
            let workflowItems = allChildren.filter { item in
                if case .workflow = item.itemType { return true }
                if case .folder = item.itemType, item.category == .workflow { return true }
                return false
            }
            let isGlobalLibrary = libraryId == LibraryManager.globalLibraryId
            let chainItems = (isGlobalLibrary && FeatureManager.shared.isWorkflowChainsEnabled)
                ? chains.map { SidebarItem.fromChain($0, libraryId: libraryId) }
                : []
            let scheduleItems = (isGlobalLibrary && FeatureManager.shared.isAutomationEnabled)
                ? schedules.map { SidebarItem.fromSchedule($0, libraryId: libraryId) }
                : []
            let triggerItems = (isGlobalLibrary && FeatureManager.shared.isAutomationEnabled)
                ? triggers.map { SidebarItem.fromTrigger($0, libraryId: libraryId) }
                : []
            let activityItems = FeatureManager.shared.isActivityEnabled
                ? unifiedActivityRuns(for: library).map { run in
                    SidebarItem(
                        id: "run:\(run.id)",
                        name: activityRunDisplayName(for: run),
                        icon: run.status.icon,
                        category: .activity,
                        itemType: .activityRun(
                            ActivityItem(
                                id: run.id,
                                type: activityType(for: run.status),
                                level: "info",
                                timestamp: ISO8601DateFormatter().string(from: run.timestamp),
                                message: run.workflowName,
                                workflowId: run.workflowId,
                                batchId: nil,
                                threadId: run.threadId,
                                nodeId: nil,
                                metadataRaw: nil,
                                durationMs: nil,
                                error: nil
                            )
                        ),
                        children: nil,
                        progress: run.progress,
                        showProgress: run.isLive,
                        libraryId: libraryId,
                        folderPath: "/",
                        sortOrder: 0,
                        isFolder: false
                    )
                }
                : []
            let buckets = UnifiedLibraryBuckets(
                documentItems: documentItems,
                searchItems: searchItems,
                workflowItems: workflowItems,
                chainItems: chainItems,
                scheduleItems: scheduleItems,
                triggerItems: triggerItems,
                activityItems: activityItems
            )

            let totalCount = documentItems.count + searchItems.count + workflowItems.count + chainItems.count +
                scheduleItems.count + triggerItems.count + activityItems.count

            if library.id == LibraryManager.globalLibraryId {
                // Global library is headless — with a single library in
                // 0.0.2 there's nothing to switch between, so the
                // "Global" row was dead chrome (#608). Library-root
                // Finder drops still work via the section headers
                // inside (Library / Saved Searches / etc.).
                unifiedLibrarySections(
                    libraryId: libraryId,
                    buckets: buckets
                )
            } else {
                DisclosureGroup(
                    isExpanded: Binding(
                        get: { sidebarState.isLibraryExpanded(library.id) },
                        set: { sidebarState.libraryExpansionStates[library.id.uuidString] = $0 }
                    )
                ) {
                    unifiedLibrarySections(
                        libraryId: libraryId,
                        buckets: buckets
                    )
                } label: {
                    LibrarySectionHeader(
                        library: library,
                        itemCount: totalCount,
                        isCurrentLibrary: library.id == windowState.libraryId,
                        onFileDrop: { urls in
                            let fileURLs = urls.filter { $0.isFileURL }
                            guard !fileURLs.isEmpty else { return false }
                            // Route to Inbox — bare files at library root are
                            // invisible in the sidebar since only folders appear there.
                            let inboxId = library.documentStore.collections.first(where: {
                                $0.name == "Inbox" && $0.parentId == nil && $0.docType == .folder
                            })?.id
                            Task {
                                do {
                                    _ = try await library.importService.importFiles(
                                        fileURLs,
                                        mode: .link,
                                        parentId: inboxId
                                    )
                                    await library.documentStore.refresh()
                                    try? await Task.sleep(for: .milliseconds(500))
                                    await library.documentStore.refresh()
                                } catch {
                                    Logger(subsystem: "com.tubb.Fichero", category: "LibraryHeaderDrop")
                                        .error("Library root drop failed: \(error.localizedDescription)")
                                }
                            }
                            return true
                        }
                    )
                    .contextMenu {
                        if library.id != LibraryManager.globalLibraryId {
                            Button("Rename Library…") {
                                libraryToRenameId = library.id
                                pendingLibraryName = library.displayName
                                showingRenameLibraryPrompt = true
                            }
                        }
                    }
                    .selectionDisabled()
                }
                .listRowInsets(EdgeInsets(top: 2, leading: 8, bottom: 2, trailing: 8))
            }
        }
    }

    @ViewBuilder
    private func unifiedLibrarySections(
        libraryId: UUID,
        buckets: UnifiedLibraryBuckets
    ) -> some View {
        unifiedDisclosureSection(
            title: "Library",
            sectionKey: "library",
            libraryId: libraryId,
            items: buckets.documentItems
        )

        if FeatureManager.shared.isSearchEnabled {
            unifiedDisclosureSection(
                title: "Saved Searches",
                sectionKey: "search",
                libraryId: libraryId,
                items: buckets.searchItems
            )
        }

        if FeatureManager.shared.isWorkflowsEnabled {
            unifiedDisclosureSection(
                title: "Workflows",
                sectionKey: "workflows",
                libraryId: libraryId,
                items: buckets.workflowItems + buckets.chainItems
            )
        }

        if FeatureManager.shared.isAutomationEnabled {
            unifiedDisclosureSection(
                title: "Automation",
                sectionKey: "automation",
                libraryId: libraryId,
                items: buckets.scheduleItems + buckets.triggerItems
            )
        }

        if FeatureManager.shared.isActivityEnabled {
            activityNavigationRow()
        }
    }

    @ViewBuilder
    private func unifiedRows(
        _ items: [SidebarItem],
        libraryId: UUID? = nil
    ) -> some View {
        // Plain ForEach — no between-row spacer rows (rejected in #620
        // because they inflated into visible empty gaps).
        //
        // Cross-hierarchy insertion lines come from `.overlay` drop
        // strips on the row's top + bottom edges (3pt each). Overlays
        // live INSIDE each row's existing frame so they don't allocate
        // new List rows. The top strip on row N = "insert at offset N";
        // the bottom strip on the LAST row = "insert at end". Non-last
        // bottom strips are redundant with the next row's top, so we
        // skip them.
        ForEach(Array(items.enumerated()), id: \.element.id) { index, item in
            unifiedRow(for: item)
                .overlay(alignment: .top) {
                    SidebarInsertionLine { droppedIds in
                        handleExternalInsertionDrop(
                            droppedIds: droppedIds,
                            at: index,
                            into: items,
                            libraryId: libraryId
                        )
                    }
                }
                .overlay(alignment: .bottom) {
                    if index == items.count - 1 {
                        SidebarInsertionLine { droppedIds in
                            handleExternalInsertionDrop(
                                droppedIds: droppedIds,
                                at: index + 1,
                                into: items,
                                libraryId: libraryId
                            )
                        }
                    }
                }
        }
        .onMove { source, destination in
            // Defensive Inbox guard (belt + suspenders with `.moveDisabled`).
            if source.contains(where: { items[$0].icon == "tray.fill" }) {
                return
            }
            guard let libraryId = libraryId,
                  let library = libraryManager.getLibrary(id: libraryId) else { return }

            // Dispatch by section kind: documents, saved searches, and
            // workflows each have their own reorder endpoint (#611).
            // Items in a DisclosureGroup section are homogeneous, so we
            // pick the kind from the first movable item and route
            // accordingly.
            var reordered = items
            reordered.move(fromOffsets: source, toOffset: destination)
            let kind = items.first.map { SidebarItemKind(prefixedId: $0.id) } ?? .unknown

            switch kind {
            case .document, .folder:
                if let orderedIds = sidebarReorderedDocIds(
                    children: items,
                    moving: source,
                    to: destination
                ) {
                    library.documentStore.reorderChildrenOptimistically(orderedIds: orderedIds)
                }
            case .savedSearch:
                let ordered = reordered.compactMap { item -> String? in
                    guard case .savedSearch(let search) = item.itemType else { return nil }
                    return search.id
                }
                guard !ordered.isEmpty else { return }
                Task {
                    try? await library.savedSearchServiceGenerated.reorderSavedSearches(ordered)
                    try? await library.savedSearchServiceGenerated.loadSavedSearches()
                }
            case .workflow, .chain:
                let ordered = reordered.compactMap { item -> String? in
                    if case .workflow(let workflow) = item.itemType { return workflow.id }
                    return nil
                }
                guard !ordered.isEmpty else { return }
                Task {
                    try? await library.workflowServiceGenerated.reorderWorkflows(ordered)
                    try? await library.workflowStore.loadWorkflows()
                }
            default:
                return
            }
        }
    }

    /// Activity rows need a tap gesture to read `modifierFlags` for
    /// cmd-click multi-select — `List(selection:)`'s `String?` binding
    /// can't express a `Set<String>`. All other rows rely on native
    /// List selection via `.tag(item.id)`.
    @ViewBuilder
    private func unifiedRow(for item: SidebarItem) -> some View {
        // `.moveDisabled` blocks AppKit-level reorder drag on Inbox
        // (#621). `.draggable` alone is insufficient because `.onMove`
        // on the ForEach lets the List's underlying NSTableView drag
        // any row for reorder, bypassing the `.draggable` gate.
        let row = SidebarItemRow(
            item: item,
            allCachedItems: allCachedItems,
            expandedItems: Binding(
                get: { sidebarState.expandedItems },
                set: { sidebarState.expandedItems = $0 }
            ),
            selectedItemId: $selectedItemId,
            renameState: renameState,
            deleteState: deleteState,
            libraryManager: libraryManager
        )
        .contentShape(Rectangle())
        .listRowInsets(EdgeInsets(top: 0, leading: 12, bottom: 0, trailing: 8))
        .moveDisabled(item.icon == "tray.fill")
        .tag(item.id)

        if item.category == .activity {
            row.simultaneousGesture(
                TapGesture().onEnded { handleUnifiedRowTap(item) }
            )
        } else {
            row
        }
    }

    /// Cross-hierarchy insert: reparent dragged docs to library root
    /// and drop them at position `offset` in the root's children.
    /// Called by overlay insertion-line strips in `unifiedRows`.
    ///
    /// Guards:
    ///   - Only "doc:" prefixed IDs (documents / folders) accepted.
    ///   - No cycle check needed: library root has no ancestors, so
    ///     any item can become a root child without forming a loop.
    private func handleExternalInsertionDrop(
        droppedIds: [String],
        at offset: Int,
        into items: [SidebarItem],
        libraryId: UUID?
    ) {
        guard let libraryId = libraryId,
              let library = libraryManager.getLibrary(id: libraryId) else { return }

        let bareIds = droppedIds
            .filter { $0.hasPrefix("doc:") }
            .map { extractActualId(from: $0) }

        guard let newOrder = sidebarReorderedDocIdsWithInsert(
            children: items,
            inserting: bareIds,
            at: offset
        ) else { return }

        Task {
            for bareId in bareIds {
                _ = try? await library.documentStore.moveDocument(bareId, toParent: nil)
            }
            await MainActor.run {
                library.documentStore.reorderChildrenOptimistically(orderedIds: newOrder)
            }
        }
    }

    // MARK: - Activity Navigation Row

    /// Single non-expandable "Activity" row — clicking navigates to the activity browser.
    /// Styled like a section header so it sits naturally below Workflows.
    @ViewBuilder
    private func activityNavigationRow() -> some View {
        let isActive: Bool = {
            if case .activity = viewMode { return true }
            return false
        }()

        Button {
            sidebarMode = .activity
            viewMode = .activity(nil)
            selectedItemId = "activity-browser"
        } label: {
            HStack(spacing: 0) {
                Text("Activity")
                    .font(.caption)
                    .fontWeight(.bold)
                    .foregroundStyle(.primary)
                Spacer()
                if executionObserver.isAnyWorkflowRunning {
                    Image(systemName: "play.circle.fill")
                        .font(.caption)
                        .foregroundStyle(.blue)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .padding(.vertical, 3)
        .padding(.horizontal, 4)
        .background(
            RoundedRectangle(cornerRadius: 4)
                .fill(isActive ? Color.accentColor.opacity(0.15) : Color.clear)
        )
        .listRowInsets(EdgeInsets(top: 0, leading: 16, bottom: 0, trailing: 8))
        .listRowSeparator(.hidden)
        .listRowBackground(Color.clear)
    }

    // MARK: - Compact Activity Grid (no longer used for section — struct kept for reuse)

    @ViewBuilder
    private func activityDisclosureSection(
        sectionKey: String,
        libraryId: UUID,
        items: [SidebarItem]
    ) -> some View {
        if !items.isEmpty {
            DisclosureGroup(
                isExpanded: Binding(
                    get: { isUnifiedSectionExpanded(libraryId: libraryId, sectionKey: sectionKey) },
                    set: { setUnifiedSectionExpanded($0, libraryId: libraryId, sectionKey: sectionKey) }
                ),
                content: {
                    // Entire run history in one list row — compact icon grid
                    activityRunsGrid(items)
                        .listRowInsets(EdgeInsets(top: 4, leading: 12, bottom: 4, trailing: 8))
                        .listRowSeparator(.hidden)
                        .listRowBackground(Color.clear)
                },
                label: {
                    Text("Activity")
                        .font(.caption)
                        .fontWeight(.bold)
                        .foregroundStyle(.primary)
                        .selectionDisabled()
                }
            )
        }
    }

    @ViewBuilder
    private func activityRunsGrid(_ items: [SidebarItem]) -> some View {
        let columns = [GridItem(.adaptive(minimum: 46, maximum: 60), spacing: 4)]
        LazyVGrid(columns: columns, alignment: .leading, spacing: 6) {
            ForEach(items) { item in
                ActivityRunGridCell(
                    item: item,
                    isSelected: selectedItemId == item.id
                )
                .onTapGesture { handleUnifiedRowTap(item) }
            }
        }
        .padding(.vertical, 4)
        .animation(.default, value: items.map(\.id))
    }

    @ViewBuilder
    private func unifiedDisclosureSection(
        title: String,
        sectionKey: String,
        libraryId: UUID,
        items: [SidebarItem]
    ) -> some View {
        if !items.isEmpty {
            DisclosureGroup(
                isExpanded: Binding(
                    get: { isUnifiedSectionExpanded(libraryId: libraryId, sectionKey: sectionKey) },
                    set: { setUnifiedSectionExpanded($0, libraryId: libraryId, sectionKey: sectionKey) }
                ),
                content: {
                    unifiedRows(items, libraryId: libraryId)
                },
                label: {
                    Text(title)
                        .font(.caption)
                        .fontWeight(.bold)
                        .foregroundStyle(.primary)
                        .selectionDisabled()
                }
            )
        }
    }

    private func unifiedSectionStorageKey(libraryId: UUID, sectionKey: String) -> String {
        "unified-section:\(libraryId.uuidString):\(sectionKey)"
    }

    private func isUnifiedSectionExpanded(libraryId: UUID, sectionKey: String) -> Bool {
        let key = unifiedSectionStorageKey(libraryId: libraryId, sectionKey: sectionKey)
        return sidebarState.unifiedSectionExpansionStates[key] ?? true
    }

    private func setUnifiedSectionExpanded(_ expanded: Bool, libraryId: UUID, sectionKey: String) {
        let key = unifiedSectionStorageKey(libraryId: libraryId, sectionKey: sectionKey)
        sidebarState.unifiedSectionExpansionStates[key] = expanded
    }

    private func handleUnifiedRowTap(_ item: SidebarItem) {
        guard item.category == .activity else { return }

        let isCommandDown = NSApp.currentEvent?.modifierFlags.contains(.command) ?? false
        if isCommandDown {
            if selectedActivityItemIds.contains(item.id) {
                selectedActivityItemIds.remove(item.id)
            } else {
                selectedActivityItemIds.insert(item.id)
            }
            selectedItemId = selectedActivityItemIds.count == 1 ? selectedActivityItemIds.first : nil
            return
        }

        selectedActivityItemIds = [item.id]
        selectedItemId = item.id
    }

    private func deleteSelectedActivityRuns() {
        guard !selectedActivityItemIds.isEmpty else { return }

        for selectedId in selectedActivityItemIds {
            guard selectedId.hasPrefix("run:") else { continue }
            let rawToken = String(selectedId.dropFirst("run:".count))
            let parts = rawToken.split(separator: "|", maxSplits: 1).map(String.init)
            guard parts.count == 2, let libraryId = UUID(uuidString: parts[0]) else { continue }
            let threadToken = parts[1]

            guard var items = historicalRunsByLibrary[libraryId] else { continue }
            items.removeAll { item in
                let candidate = item.threadId ?? item.batchId.map { "batch:\($0)" }
                return candidate == threadToken
            }
            historicalRunsByLibrary[libraryId] = items
        }

        selectedActivityItemIds.removeAll()
        if selectedItemId?.hasPrefix("run:") == true {
            selectedItemId = nil
        }
        if case .activity = viewMode {
            viewMode = .activity(nil)
        }
    }

    @MainActor
    private func unifiedActivityRuns(for library: LibraryManager.LibraryReference) -> [ActivityRun] {
        runsByWorkflow(
            for: library,
            activeExecutions: executionObserver.activeExecutions,
            historicalRuns: historicalRunsByLibrary
        )
        .values
        .flatMap { $0 }
        .sorted { $0.timestamp > $1.timestamp }
    }

    private func activityType(for status: ActivityRunStatus) -> String {
        switch status {
        case .running:
            return "workflow_started"
        case .completed:
            return "workflow_completed"
        case .failed:
            return "workflow_failed"
        case .cancelled:
            return "workflow_cancelled"
        }
    }

    @MainActor
    func unifiedSelectedRun(forSidebarId sidebarId: String) -> ActivityRun? {
        guard sidebarId.hasPrefix("run:") else { return nil }
        let runSidebarId = String(sidebarId.dropFirst("run:".count))
        for library in libraryManager.openLibraries {
            if let run = unifiedActivityRuns(for: library).first(where: { $0.id == runSidebarId }) {
                return run
            }
        }
        return nil
    }

}

// MARK: - Activity Run Grid Cell

/// Compact icon cell for the Activity sidebar grid.
/// Shows a status icon + short time (e.g. "7:05 PM") in a ~46pt square.
struct ActivityRunGridCell: View {
    let item: SidebarItem
    let isSelected: Bool

    var body: some View {
        VStack(spacing: 2) {
            Image(systemName: item.icon)
                .font(.system(size: 18))
                .foregroundStyle(iconColor)
            Text(shortTime)
                .font(.system(size: 9))
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 5)
        .padding(.horizontal, 3)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(isSelected ? Color.accentColor.opacity(0.2) : Color.clear)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 6)
                .strokeBorder(isSelected ? Color.accentColor.opacity(0.5) : Color.clear, lineWidth: 1)
        )
    }

    private var shortTime: String {
        // "Today 7:05 PM" → "7:05 PM"; fall back to full name
        let parts = item.name.split(separator: " ", maxSplits: 1)
        return parts.count > 1 ? String(parts[1]) : item.name
    }

    private var iconColor: Color {
        switch item.icon {
        case "checkmark.circle.fill": return .green
        case "xmark.circle.fill": return .red
        case "play.circle.fill": return .blue
        case "stop.circle.fill": return .orange
        default: return .secondary
        }
    }
}

// MARK: - Insertion Line Overlay

/// Edge-aligned overlay strip that acts as a cross-hierarchy
/// drop target. Lives INSIDE a row's own frame (no new List row =
/// no empty gap regression from #620). 3pt hit region; paints a
/// 2pt accent line when targeted so it reads as an insertion
/// indicator between rows.
///
/// Only internal sidebar drags (utf8PlainText from `.draggable(item.id)`)
/// route through this handler — Finder drops still hit the inner
/// row's `.onDrop` and go through the file-import path.
struct SidebarInsertionLine: View {
    let onDrop: (_ droppedIds: [String]) -> Void

    @State private var isTargeted = false

    var body: some View {
        Rectangle()
            .fill(isTargeted ? Color.accentColor : Color.clear)
            .frame(height: isTargeted ? 2 : 3)
            .frame(maxWidth: .infinity)
            .contentShape(Rectangle())
            .allowsHitTesting(true)
            .onDrop(of: [UTType.utf8PlainText], isTargeted: $isTargeted) { providers in
                let textProviders = providers.filter {
                    $0.canLoadObject(ofClass: NSString.self)
                }
                guard !textProviders.isEmpty else { return false }
                Task {
                    var ids: [String] = []
                    for provider in textProviders {
                        if let str = try? await Self.loadString(from: provider) {
                            ids.append(str)
                        }
                    }
                    guard !ids.isEmpty else { return }
                    await MainActor.run { onDrop(ids) }
                }
                return true
            }
    }

    private static func loadString(from provider: NSItemProvider) async throws -> String {
        try await withCheckedThrowingContinuation { continuation in
            _ = provider.loadObject(ofClass: NSString.self) { value, error in
                if let error {
                    continuation.resume(throwing: error)
                } else if let nsString = value as? NSString {
                    continuation.resume(returning: nsString as String)
                } else {
                    continuation.resume(throwing: NSError(domain: "SidebarInsertionLine", code: -1))
                }
            }
        }
    }
}
