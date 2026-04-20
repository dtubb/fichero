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
                // Global library stays always expanded.
                Section {
                    unifiedLibrarySections(
                        libraryId: libraryId,
                        buckets: buckets
                    )
                } header: {
                    LibrarySectionHeader(
                        library: library,
                        itemCount: totalCount,
                        isCurrentLibrary: library.id == windowState.libraryId,
                        onFileDrop: { urls in
                            // Import Finder drops at library root. Previously
                            // these went nowhere (#582) — no drop destination
                            // existed on the library header.
                            let fileURLs = urls.filter { $0.isFileURL }
                            guard !fileURLs.isEmpty else { return false }
                            Task {
                                do {
                                    _ = try await library.importService.importFiles(
                                        fileURLs,
                                        mode: .link,
                                        parentId: nil
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
                            // Import Finder drops at library root. Previously
                            // these went nowhere (#582) — no drop destination
                            // existed on the library header.
                            let fileURLs = urls.filter { $0.isFileURL }
                            guard !fileURLs.isEmpty else { return false }
                            Task {
                                do {
                                    _ = try await library.importService.importFiles(
                                        fileURLs,
                                        mode: .link,
                                        parentId: nil
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
            unifiedDisclosureSection(
                title: "Activity",
                sectionKey: "activity",
                libraryId: libraryId,
                items: buckets.activityItems
            )
        }
    }

    @ViewBuilder
    private func unifiedRows(
        _ items: [SidebarItem],
        libraryId: UUID? = nil
    ) -> some View {
        // Insertion spacers between each row + one at the end so users
        // can drop a dragged folder/PDF at a precise position to
        // become a sibling at THIS level (reparenting to library root).
        // Visual + drop-target via `SidebarInsertionSpacer` because
        // SwiftUI's `.dropDestination(for:)` on ForEach doesn't render
        // insertion lines inside DisclosureGroup content.
        ForEach(Array(items.enumerated()), id: \.element.id) { index, item in
            SidebarInsertionSpacer(offset: index) { droppedIds, offset in
                handleExternalInsertionDrop(
                    droppedIds: droppedIds,
                    at: offset,
                    into: items,
                    libraryId: libraryId
                )
            }
            unifiedRow(for: item)
        }
        // `.onMove` on the ForEach for same-list reorder (native
        // insertion indicator works for reorder even without the
        // spacer hack).
        .onMove { source, destination in
            guard let libraryId = libraryId,
                  let library = libraryManager.getLibrary(id: libraryId),
                  let orderedIds = sidebarReorderedDocIds(
                      children: items,
                      moving: source,
                      to: destination
                  ) else { return }
            library.documentStore.reorderChildrenOptimistically(orderedIds: orderedIds)
        }
        // Trailing spacer after the last row so users can drop past the
        // final sibling to insert at the end.
        SidebarInsertionSpacer(offset: items.count) { droppedIds, offset in
            handleExternalInsertionDrop(
                droppedIds: droppedIds,
                at: offset,
                into: items,
                libraryId: libraryId
            )
        }
    }

    /// Reparent sidebar-dragged documents to the library root and reorder
    /// so the new docs sit at `offset` within the root's children.
    /// Target is always library root here (parentId = nil) since
    /// unifiedRows is only called for top-level rendering.
    ///
    /// Guards:
    ///   - Only "doc:" prefixed ids (documents / folders) are accepted —
    ///     saved searches, workflows, etc. have distinct reorder paths.
    ///   - No cycle check needed: library root has no ancestors, so
    ///     moving any item to root can't create a cycle.
    ///
    /// Shares its insertion-math with `handleNestedInsertionDrop` via
    /// the pure `sidebarReorderedDocIdsWithInsert` helper.
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

    /// Activity rows need a tap gesture to read `modifierFlags` for
    /// cmd-click multi-select — `List(selection:)`'s `String?` binding
    /// can't express a `Set<String>`. All other rows rely on native
    /// List selection via `.tag(item.id)`.
    @ViewBuilder
    private func unifiedRow(for item: SidebarItem) -> some View {
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
        .tag(item.id)

        if item.category == .activity {
            row.simultaneousGesture(
                TapGesture().onEnded { handleUnifiedRowTap(item) }
            )
        } else {
            row
        }
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

// MARK: - Insertion Spacer

/// Thin horizontal drop target between sibling rows. Enables precise
/// insertion-line drops that SwiftUI's `.dropDestination(for:)` on
/// ForEach doesn't provide inside DisclosureGroup content.
///
/// Payload: `utf8PlainText` (matches `.draggable(item.id)` String
/// Transferable). 2pt tall at rest, 3pt accent-blue while targeted.
struct SidebarInsertionSpacer: View {
    let offset: Int
    let onDrop: (_ droppedIds: [String], _ at: Int) -> Void

    @State private var isTargeted = false

    var body: some View {
        Rectangle()
            .fill(isTargeted ? Color.accentColor : Color.clear)
            .frame(height: isTargeted ? 3 : 2)
            .frame(maxWidth: .infinity)
            .contentShape(Rectangle())
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
                    await MainActor.run {
                        onDrop(ids, offset)
                    }
                }
                return true
            }
            // EdgeInsets() (all zero) lets macOS List collapse the row to
            // fit the 2pt Rectangle. Any non-zero inset (even horizontal)
            // causes List to apply its default minimum row height — which
            // inflates every spacer into a visible ~24pt gap (#620).
            .listRowInsets(EdgeInsets())
            .listRowSeparator(.hidden)
            .listRowBackground(Color.clear)
            .selectionDisabled()
    }

    private static func loadString(from provider: NSItemProvider) async throws -> String {
        try await withCheckedThrowingContinuation { continuation in
            _ = provider.loadObject(ofClass: NSString.self) { value, error in
                if let error {
                    continuation.resume(throwing: error)
                } else if let nsString = value as? NSString {
                    continuation.resume(returning: nsString as String)
                } else {
                    continuation.resume(throwing: NSError(domain: "SidebarInsertionSpacer", code: -1))
                }
            }
        }
    }
}
