import SwiftUI

/// The Inspector's **Activity** section (`activity.pane.inspector-shows-the-selected-row`, #6441): the ONE details view for
/// the Activity pane's selected row, mounted here and nowhere else, and under it the versions of each step that ran more
/// than once (`activity.pane.versions-are-siblings`), the version that counts marked. Nothing selected shows nothing.
struct ActivityInspectorSection: View {
    let pick: ActivityPaneSelection?
    @Environment(LibraryManager.self) private var libraryManager

    var body: some View {
        if let pick, let library = library(pick.selection.libraryId) {
            VStack(alignment: .leading, spacing: 0) {
                ActivityDetailsView(selection: pick.selection)
                    .libraryServiceEnvironment(library)
                if !pick.versions.isEmpty {
                    Divider()
                    ActivityVersionsList(versions: pick.versions)
                }
            }
            .accessibilityIdentifier("inspector.activity")
        } else {
            Color.clear  // nothing selected: an empty section (`activity.window.no-empty-prose`)
        }
    }

    private func library(_ id: UUID?) -> LibraryManager.LibraryReference? {
        id.flatMap { libraryManager.getLibrary(id: $0) } ?? libraryManager.globalLibrary
    }
}

/// A step's versions side by side, newest first: model, result, time, cost, and the one that counts.
struct ActivityVersionsList: View {
    let versions: [ActivityPane.StepVersions]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(versions) { step in
                Text(step.step).font(.headline)
                Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 4) {
                    ForEach(step.versions) { version in
                        GridRow {
                            let glyph = ActivityPane.glyph(version)
                            Image(systemName: glyph.symbol ?? "circle.dotted")
                                .foregroundStyle(glyph.isFailure ? AnyShapeStyle(.red) : AnyShapeStyle(.secondary))
                                .accessibilityLabel(glyph.word)
                            Text(version.model ?? "—").lineLimit(1)
                            Text("\(version.done) of \(version.total)").monospacedDigit()
                            Text(ActivityPane.timeLine(version)).monospacedDigit()
                            Text(ActivityPane.costLine(version)).monospacedDigit()
                            Text(version.counts ? "counts" : "").foregroundStyle(.secondary)
                        }
                        .font(.callout)
                    }
                }
            }
        }
        .padding(12)
        .accessibilityIdentifier("inspector.activity.versions")
    }
}

#Preview("A step read twice") {
    func step(_ id: String, model: String, phase: ActivityMonitorRow.Phase) -> ActivityMonitorRow {
        ActivityMonitorRow(id: id, kind: .step, libraryId: nil, runRowID: "run", runThreadId: "run", jobId: id, name: "Read",
                           projectName: nil, phase: phase, reason: nil, workingOn: nil, done: 10, total: 10, started: nil,
                           seconds: 62, costUsd: 0.42, tokens: 1, errors: 0, model: model, isLive: false, children: nil)
    }
    var counting = step("b", model: "Qwen 2 VL", phase: .done)
    counting.counts = true
    return ActivityVersionsList(versions: [
        ActivityPane.StepVersions(step: "Read", versions: [counting, step("a", model: "Kraken", phase: .failed)])
    ])
    .frame(width: 320)
}
