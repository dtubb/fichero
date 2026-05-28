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
        if sidebarMode == .mindPalace {
            // Mind Palace mode shows its rooms list here; the canvas + node
            // inspector render in the main content area (MindPalaceContainer).
            RoomListView()
        } else {
            standardSidebarContent
        }
    }

    @ViewBuilder
    var standardSidebarContent: some View {
        VStack(spacing: 0) {
            // Breathing room between the window's title bar and the sidebar's
            // first row. Without this the 'Library' header sits flush against
            // the toolbar — feels cramped on macOS Tahoe / Sequoia. 12pt
            // matches Mail.app / Finder.app's sidebar-to-toolbar gap. (#883)
            Spacer()
                .frame(height: 12)

            if sidebarMode == .research {
                ResearchProjectListView()
            } else {
                unifiedContent
            }

            // Bottom toolbar (not shown for research — ResearchProjectListView has its own)
            if shouldShowBottomToolbar && sidebarMode != .research {
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
        // #883 — paint over the default sidebar NSVisualEffectView
        // (which renders darker than the content area) with the window
        // background colour so the sidebar tonally matches the content
        // pane. scrollContentBackground(.hidden) alone wasn't enough on
        // macOS — the NavigationSplitView's sidebar column has its own
        // material layer underneath. .background here paints over that.
        .background(Color(NSColor.windowBackgroundColor))
        .onDeleteCommand {
            deleteSelectedActivityRuns()
        }
    }

    @ViewBuilder
    // swiftlint:disable:next function_body_length
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
                    libraryDisclosureLabel(library: library, totalCount: totalCount)
                        .selectionDisabled()
                }
                .listRowInsets(EdgeInsets(top: 2, leading: 8, bottom: 2, trailing: 8))
            }
        }
    }

    @ViewBuilder
    private func libraryDisclosureLabel(
        library: LibraryManager.LibraryReference,
        totalCount: Int
    ) -> some View {
        LibrarySectionHeader(
            library: library,
            itemCount: totalCount,
            isCurrentLibrary: library.id == windowState.libraryId,
            onFileDrop: { [library] urls in handleLibraryHeaderDrop(urls, library: library) },
            onSidebarItemDrop: { [library] droppedIds in
                handleLibraryHeaderItemDrop(droppedIds: droppedIds, library: library)
            },
            onTap: {
                if windowState.libraryId != library.id { windowState.libraryId = library.id }
                sidebarMode = .library
                viewMode = .library(nil)
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
    }

    @ViewBuilder
    private func unifiedLibrarySections(
        libraryId: UUID,
        buckets: UnifiedLibraryBuckets
    ) -> some View {
        unifiedDisclosureSection(
            title: "Library",
            icon: "books.vertical",
            sectionKey: "library",
            libraryId: libraryId,
            items: buckets.documentItems
        )

        // Visual separator between document library and tools section
        Divider()
            .listRowInsets(EdgeInsets(top: 4, leading: 8, bottom: 4, trailing: 8))
            .listRowSeparator(.hidden)
            .listRowBackground(Color.clear)

        if FeatureManager.shared.isWorkflowsEnabled {
            workflowsNavigationRow()
        }

        if FeatureManager.shared.isAutomationEnabled {
            unifiedDisclosureSection(
                title: "Automation",
                icon: "gearshape.2",
                sectionKey: "automation",
                libraryId: libraryId,
                items: buckets.scheduleItems + buckets.triggerItems
            )
        }

        if FeatureManager.shared.isActivityEnabled {
            activityNavigationRow()
        }

        // Saved Searches at the bottom — Daniel: 'saved searches should
        // be down beside Workflows and Activity'. Mental model: Library
        // is the source-of-truth tree; Workflows / Activity / Saved
        // Searches are *tools and history* over that tree, so they
        // belong together below the library.
        if FeatureManager.shared.isSearchEnabled {
            unifiedDisclosureSection(
                title: "Saved Searches",
                icon: "magnifyingglass",
                sectionKey: "search",
                libraryId: libraryId,
                items: buckets.searchItems
            )
        }
    }

    @ViewBuilder
    private func unifiedRows(
        _ items: [SidebarItem],
        libraryId: UUID? = nil
    ) -> some View {
        // Cross-hierarchy / cross-section drops at the root level use
        // `.dropDestination(for:action:)` on the ForEach — SwiftUI's
        // built-in between-row insertion API, which receives the offset
        // natively (no custom overlay strip needed). Same-section
        // reorder still goes through `.onMove` and shows the system's
        // row-drop indicator.
        ForEach(Array(items.enumerated()), id: \.element.id) { _, item in
            unifiedRow(for: item)
        }
        .dropDestination(for: SidebarDragID.self) { ids, offset in
            sidebarRowLogger.debug("🎯 unifiedRows .dropDestination FIRED with \(ids.count) ids at offset \(offset)")
            handleExternalInsertionDrop(
                droppedIds: ids.map(\.id),
                at: offset,
                into: items,
                libraryId: libraryId
            )
        }
        .onMove { source, destination in
            handleUnifiedRowsMove(source: source, destination: destination, items: items, libraryId: libraryId)
        }
    }

    // swiftlint:disable:next cyclomatic_complexity
    private func handleUnifiedRowsMove(
        source: IndexSet,
        destination: Int,
        items: [SidebarItem],
        libraryId: UUID?
    ) {
        let sourceDesc = source.map(\.description).joined(separator: ",")
        sidebarRowLogger.debug(
            "🔵 unifiedRows .onMove FIRED — source=\(sourceDesc) dest=\(destination) items=\(items.count)"
        )

        // Defensive Inbox guard (belt + suspenders with `.moveDisabled`).
        if source.contains(where: { items[$0].icon == "tray.fill" }) {
            sidebarRowLogger.debug("🔵 unifiedRows .onMove BAILED — Inbox guard")
            return
        }
        guard let libraryId, let library = libraryManager.getLibrary(id: libraryId) else {
            sidebarRowLogger.debug("🔵 unifiedRows .onMove BAILED — no libraryId/library")
            return
        }

        // Dispatch by section kind — documents, saved searches, and workflows
        // each have their own reorder endpoint (#611).
        var reordered = items
        reordered.move(fromOffsets: source, toOffset: destination)
        let kind = items.first.map { SidebarItemKind(prefixedId: $0.id) } ?? .unknown

        switch kind {
        case .document, .folder:
            if let orderedIds = sidebarReorderedDocIds(children: items, moving: source, to: destination) {
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
                await library.workflowStore.loadWorkflows()
            }
        default:
            return
        }
    }

    /// Activity rows need a tap gesture to read `modifierFlags` for
    /// cmd-click multi-select — `List(selection:)`'s `String?` binding
    /// can't express a `Set<String>`. All other rows rely on native
    /// List selection via `.tag(item.id)`.
    @ViewBuilder
    private func unifiedRow(for item: SidebarItem) -> some View {
        // `.moveDisabled` blocks AppKit-level reorder drag on Inbox
        // (#621). `.draggable` lives here on the row container — not
        // inside SidebarItemRow's body — so NSTableView's native
        // row-drag picks up the Transferable uniformly across the
        // whole row (including taps on the inner icon/name).
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
        .draggable(item.icon == "tray.fill" ? SidebarDragID(id: "") : SidebarDragID(id: item.id))
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
    /// Styled as a regular sidebar leaf row (icon + normal-weight label) matching
    /// Inbox / folder rows. Bold section-header style removed in #655.
    @ViewBuilder
    private func activityNavigationRow() -> some View {
        Label {
            HStack(spacing: 4) {
                Text("Activity")
                    .lineLimit(1)
                if executionObserver.isAnyWorkflowRunning {
                    // Spinner instead of static play.circle so it's clear
                    // something is actively in flight (#785). Daniel: "the
                    // blue dot in activity is also not a spinner".
                    ProgressView()
                        .controlSize(.small)
                        .scaleEffect(0.7)
                }
            }
        } icon: {
            Image(systemName: "clock.arrow.circlepath")
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        // Use .tag so List(selection:) owns the tap → onChange routes to activity view.
        // A Button without .tag in sidebar List doesn't reliably fire on macOS (#647).
        .tag("activity-browser")
        .listRowInsets(EdgeInsets(top: 0, leading: 16, bottom: 0, trailing: 8))
        .listRowSeparator(.hidden)
        .listRowBackground(Color.clear)
    }

    private func workflowsNavigationRow() -> some View {
        Label("Workflows", systemImage: "bolt")
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            .tag("workflows-browser")
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
        icon: String,
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
                    Label(title, systemImage: icon)
                        .font(.caption)
                        .fontWeight(.semibold)
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

// MARK: - Library Header Helpers

extension SidebarView {
    /// Drop handler for the library disclosure-group header row.
    /// Imports dropped files into the library Inbox (or root if no Inbox exists).
    @discardableResult
    func handleLibraryHeaderDrop(_ urls: [URL], library: LibraryManager.LibraryReference) -> Bool {
        let fileURLs = urls.filter { $0.isFileURL }
        guard !fileURLs.isEmpty else { return false }
        let collections = library.documentStore.collections
        var inboxId: String?
        for col in collections where col.name == "Inbox" && col.parentId == nil && col.docType == .folder {
            inboxId = col.id
            break
        }
        Task {
            do {
                _ = try await library.importService.importFiles(fileURLs, mode: .link, parentId: inboxId)
                await library.documentStore.refresh()
                try? await Task.sleep(for: .milliseconds(500))
                await library.documentStore.refresh()
            } catch {
                Logger(subsystem: "com.fichero.fichero", category: "LibraryHeaderDrop")
                    .error("Library root drop failed: \(error.localizedDescription)")
            }
        }
        return true
    }

    /// Reparents sidebar documents dropped onto the library header to
    /// the library root (parentId = nil). After this lands, the user
    /// can drag-reorder the items at root level via native between-row
    /// drops. Saved-search / workflow / chain IDs are filtered out —
    /// they don't belong at the doc-tree root.
    func handleLibraryHeaderItemDrop(droppedIds: [String], library: LibraryManager.LibraryReference) {
        let bareIds = droppedIds
            .filter { $0.hasPrefix("doc:") }
            .map { extractActualId(from: $0) }
        guard !bareIds.isEmpty else { return }
        Task {
            for bareId in bareIds {
                _ = try? await library.documentStore.moveDocument(bareId, toParent: nil)
            }
            await library.documentStore.refresh()
        }
    }
}
