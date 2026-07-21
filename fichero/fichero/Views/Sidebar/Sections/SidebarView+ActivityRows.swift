#if canImport(AppKit)
import AppKit
#endif
import SwiftUI

// MARK: - Compact Activity Grid (no longer used for section — struct kept for reuse)

extension SidebarView {
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

    func handleUnifiedRowTap(_ item: SidebarItem) {
        guard item.category == .activity else { return }

        let isCommandDown: Bool = {
            #if canImport(AppKit)
            return NSApp.currentEvent?.modifierFlags.contains(.command) ?? false
            #else
            return false
            #endif
        }()
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

    @MainActor
    func unifiedActivityRuns(for library: LibraryManager.LibraryReference) -> [ActivityRun] {
        runsByWorkflow(
            for: library,
            activeExecutions: executionObserver.activeExecutions,
            historicalRuns: historicalRunsByLibrary
        )
        .values
        .flatMap { $0 }
        .sorted { $0.timestamp > $1.timestamp }
    }

    @MainActor
    func unifiedActivityItems(for library: LibraryManager.LibraryReference, libraryId: UUID) -> [SidebarItem] {
        unifiedActivityRuns(for: library).map { run in
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
    }

    private func activityType(for status: ActivityRunStatus) -> String {
        switch status {
        case .running, .paused:
            // `.paused` is a live (in-flight) run, not a terminal state —
            // surface it as the live-run activity type (#2631).
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
                .font(.caption2)
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
