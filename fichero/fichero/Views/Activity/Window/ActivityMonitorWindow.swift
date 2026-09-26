import SwiftUI

/// Root of the poppable "Activity" window (#2546 / B2) — ONE list of every
/// run, across every open library.
///
/// Rebuilt 2026-08-28 (Daniel: Activity should read like Mail). It used to
/// render a section per library, each an independent `ActivityBrowserView`
/// with its own store, its own poll and its own error pill, reserving 160pt
/// whether or not it held a single run; five open libraries produced five
/// mostly-empty scrolling lists and five "Couldn't load activity" banners.
///
/// Mail's unified inbox is the shape: the account — here the library — is a
/// column ON the row rather than a container around it. Runs are merged and
/// sorted live-first, so the window answers "what is happening right now"
/// without the reader scanning five lists to find out.
struct ActivityMonitorWindow: View {
    @Environment(LibraryManager.self) private var libraryManager
    @Environment(\.openWindow) private var openWindow
    @State private var selectionState = ActivityWindowSelectionState.shared
    /// Multi-select (#4960 p3: "multi-select in the window") — deliberately
    /// separate from `selectionState`, which names the ONE run the detail
    /// window follows. A bulk selection of five failed runs has no single
    /// "the" detail to show; double-clicking a row still drives the detail
    /// window through `openDetails(for:)` below, unaffected by how many rows
    /// are selected for Delete.
    @State private var selectedIDs: Set<String> = []
    /// The outcome of the last Delete/Clear Failed — surfaced plainly rather
    /// than silently, per #4960: a still-running run in the selection is
    /// SKIPPED, never force-deleted, and the reader is told which.
    @State private var deleteNotice: String?

    /// EVERY open library, global included (Daniel #19: "show ALL
    /// libraries") — the window used to show only the selection-state
    /// library, so runs in any other open library were invisible here.
    private var libraries: [LibraryManager.LibraryReference] {
        var references = libraryManager.openLibraries
        if let global = libraryManager.globalLibrary,
           !references.contains(where: { $0.id == global.id }) {
            references.append(global)
        }
        return references
    }

    var body: some View {
        Group {
            if libraries.isEmpty {
                ContentUnavailableView(
                    "No Library Open",
                    systemImage: "tray",
                    description: Text("Open a library to monitor its workflow activity.")
                )
            } else if mergedRuns.isEmpty {
                ContentUnavailableView(
                    "No Runs Yet",
                    systemImage: "clock.arrow.circlepath",
                    description: Text("Workflow runs from every open library appear here.")
                )
            } else {
                // ONE list across every open library (Daniel, 2026-08-28:
                // Activity should read like Mail). This replaced a section per
                // library, each an independent ActivityBrowserView reserving
                // 160pt whether or not it held a run: five open libraries meant
                // five scrolling lists, five polls and five error pills over
                // mostly empty space. The library is a COLUMN on the row, not a
                // container around it — which is exactly how Mail's unified
                // inbox names the account.
                List(selection: $selectedIDs) {
                    ForEach(mergedRuns) { run in
                        UnifiedActivityRow(run: run) { openDetails(for: run) }
                            .tag(run.id)
                            // Infinite scroll (#4960: dropping the old 7-day/
                            // 100-event ceiling means there is no fixed-size
                            // list any more): the last row appearing is the
                            // signal to page in the next one, per library —
                            // cheaper than a scroll-position observer, and
                            // the idiomatic SwiftUI List pattern for this.
                            .onAppear {
                                guard run.id == mergedRuns.last?.id, let library = library(for: run.libraryId)
                                else { return }
                                Task { await library.activityStore.loadMoreRuns(library: library) }
                            }
                    }
                }
                .listStyle(.inset)
                .contextMenu(forSelectionType: String.self) { ids in
                    contextMenuItems(for: ids)
                } primaryAction: { ids in
                    guard ids.count == 1, let id = ids.first,
                          let run = mergedRuns.first(where: { $0.id == id }) else { return }
                    openDetails(for: run)
                }
                .onDeleteCommand { Task { await deleteSelected() } }
            }
        }
        .navigationTitle("Activity")
        .frame(minWidth: 420, minHeight: 520)
        .toolbar {
            ToolbarItem {
                Button("Clear Failed", role: .destructive) { Task { await clearFailed() } }
                    .disabled(!mergedRuns.contains { $0.status == .failed })
            }
        }
        .safeAreaInset(edge: .bottom) {
            // Per-library load failures + the delete/Clear-Failed outcome
            // (#4960 §2: the review's verified "window ignores load
            // failures" defect — it read `runLoadFailures` from nowhere. A
            // query failure here now means the window CAN say "No Runs Yet"
            // over a library it simply couldn't read, exactly what the
            // browser already avoids via the same property).
            VStack(spacing: 0) {
                ForEach(libraries.flatMap(\.activityStore.runLoadFailures), id: \.self) { message in
                    HStack(spacing: 6) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundStyle(.orange)
                        Text(message)
                            .font(.caption)
                        Spacer(minLength: 8)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(.regularMaterial)
                }
                if let deleteNotice {
                    HStack(spacing: 6) {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundStyle(.orange)
                        Text(deleteNotice)
                            .font(.caption)
                        Spacer(minLength: 8)
                        Button("Dismiss") { self.deleteNotice = nil }
                            .font(.caption)
                            .buttonStyle(.borderless)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(.regularMaterial)
                }
            }
        }
        // The per-library sections this replaced each hosted an
        // ActivityBrowserView, and THAT view was what populated its store —
        // so merging the list without taking over the load left every store
        // empty and the window said "No Runs Yet" over a library full of runs
        // (Daniel, 2026-08-28). The window owns the refresh now.
        .task(id: refreshKey) { await refreshAll() }
    }

    @ViewBuilder
    private func contextMenuItems(for ids: Set<String>) -> some View {
        Button("Delete", role: .destructive) {
            Task { await deleteRuns(withIDs: ids) }
        }
    }

    private func library(for id: UUID?) -> LibraryManager.LibraryReference? {
        guard let id else { return nil }
        return libraries.first { $0.id == id }
    }

    /// Delete every SELECTED row — `.onDeleteCommand` (the Delete key) and
    /// the context menu's Delete both land here.
    private func deleteSelected() async {
        await deleteRuns(withIDs: selectedIDs)
    }

    /// The ONE delete operation (#4960), routed per row's OWN library since
    /// the merged list spans every open library and each library owns its
    /// own `ActivityStore`/`ActivityService`. A still-running run in the
    /// selection is SKIPPED by the engine, never force-deleted — reported
    /// plainly in `deleteNotice`, never silently dropped.
    private func deleteRuns(withIDs ids: Set<String>) async {
        let selected = mergedRuns.filter { ids.contains($0.id) }
        var skippedCount = 0
        for (libraryId, runsInLibrary) in Dictionary(grouping: selected, by: { $0.libraryId }) {
            guard let library = library(for: libraryId) else { continue }
            let outcome = await library.activityStore.deleteRuns(threadIds: runsInLibrary.map(\.runId))
            skippedCount += outcome.skippedIds.count
        }
        selectedIDs.removeAll()
        deleteNotice = skippedCount > 0 ? runsStillRunningMessage(skippedCount) : nil
    }

    /// "Clear Failed" (#4960): the SAME delete operation, a status filter
    /// instead of explicit ids, across every open library.
    private func clearFailed() async {
        var skippedCount = 0
        for library in libraries {
            let outcome = await library.activityStore.deleteRuns(statuses: ["failed"])
            skippedCount += outcome.skippedIds.count
        }
        deleteNotice = skippedCount > 0
            ? "\(skippedCount) run\(skippedCount == 1 ? "" : "s") could not be cleared."
            : nil
    }

    /// Plain grammar, not markdown inflection (`^[...](inflect: true)` only
    /// works through `Text`'s literal/`LocalizedStringResource` initializer,
    /// not a `String` built at runtime and handed to `Text(_ string:)`).
    private func runsStillRunningMessage(_ count: Int) -> String {
        "\(count) run\(count == 1 ? "" : "s") still running — not deleted."
    }

    /// Changes whenever the set of open libraries changes, or any library's
    /// live executions do — reading those counts here is also what subscribes
    /// this view to the @Observable stores, so a run starting or finishing
    /// re-runs the task above.
    private var refreshKey: String {
        libraries
            .map { "\($0.id):\($0.workflowExecutionStore.executions.count)" }
            .joined(separator: "|")
    }

    /// Select the run and open its step trace. Selection is set FIRST because
    /// the detail window resolves what to show from the shared selection state
    /// (and the `libraryId` it carries), not from a parameter.
    private func openDetails(for run: ActivityRun) {
        selectionState.select(run.toSelectedRun())
        openWindow(id: ActivityWindowSelectionState.detailWindowID)
    }

    /// Rebuild every open library's run list. Each store owns its own merge of
    /// live executions and history; this only feeds each one the dependencies
    /// it cannot reach from inside itself.
    private func refreshAll() async {
        for library in libraries {
            await library.activityStore.rebuildRuns(
                activeExecutions: Array(library.workflowExecutionStore.executions.values),
                library: library
            )
        }
    }

    /// Every open library's runs in one sequence: live runs first (the thing
    /// you opened the window to watch), then most recent. Sorting here rather
    /// than per-section is what lets the window answer "what is happening right
    /// now" without the reader scanning five lists.
    private var mergedRuns: [ActivityRun] {
        libraries
            .flatMap(\.activityStore.runs)
            .sorted { lhs, rhs in
                if lhs.isLive != rhs.isLive { return lhs.isLive }
                return lhs.timestamp > rhs.timestamp
            }
    }

}

// ActivityWindowMenuButton was deleted with #4524: the `Window("Activity")`
// scene's automatic Windows-menu item (see FicheroApp scene declarations) is
// the one entry point, so a hand-rolled CommandGroup button was a duplicate.
