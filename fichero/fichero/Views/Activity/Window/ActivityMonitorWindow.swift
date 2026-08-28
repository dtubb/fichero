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
    @State private var selectionState = ActivityWindowSelectionState.shared

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
                List(selection: selectionBinding) {
                    ForEach(mergedRuns) { run in
                        UnifiedActivityRow(run: run)
                            .tag(run.id)
                    }
                }
                .listStyle(.inset)
            }
        }
        .navigationTitle("Activity")
        .frame(minWidth: 420, minHeight: 520)
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

    /// Selection round-trips through the shared state, which already carries
    /// the `libraryId` the detail window resolves against — so a merged list
    /// keeps working with the existing detail plumbing.
    private var selectionBinding: Binding<String?> {
        Binding(
            get: {
                // SelectedActivityRun.id is the run id; the List tags rows by
                // ActivityRun.id, which is not the same key (a live run and its
                // historical record share a runId). Translate rather than
                // assume they match.
                guard let selected = selectionState.selectedRun else { return nil }
                return mergedRuns.first { $0.runId == selected.id }?.id
            },
            set: { newValue in
                guard let newValue,
                      let run = mergedRuns.first(where: { $0.id == newValue })
                else { return }
                selectionState.select(run.toSelectedRun())
            }
        )
    }

}

// ActivityWindowMenuButton was deleted with #4524: the `Window("Activity")`
// scene's automatic Windows-menu item (see FicheroApp scene declarations) is
// the one entry point, so a hand-rolled CommandGroup button was a duplicate.
