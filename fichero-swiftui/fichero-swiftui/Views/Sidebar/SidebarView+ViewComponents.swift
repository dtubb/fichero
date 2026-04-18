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
        ForEach(items) { item in
            unifiedRow(for: item)
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
                    // SimpleSidebar-style section header: compact,
                    // bold, primary-foreground so it reads as a clear
                    // section marker rather than greyed-out filler.
                    // Matches SimpleSidebarUI's
                    // `.font(.system(size: 10)).fontWeight(.bold)`.
                    Text(title)
                        .font(.caption)
                        .fontWeight(.bold)
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
