import SwiftUI

/// Under a line whose shape changed after a paid cloud model read it: the words may be out of date, and reading again is
/// the person's call (it costs). Also says so when a re-read could not be queued (`segment-actions.automatic-rerun-after-an-edit`).
struct StaleReadingBar: View {
    let segmentId: String

    var body: some View {
        let state = SegmentRereadState.shared
        if let failure = state.failed[segmentId] {
            Text(failure).font(.caption).foregroundStyle(.red).padding(4)
        } else if state.stale.contains(segmentId) {
            HStack(spacing: 6) {
                Text("Text may be out of date:").font(.caption).foregroundStyle(.secondary)
                RunStepOnSegmentsMenu(ids: [segmentId], label: SegmentReread.againTitle)
                    .menuStyle(.borderlessButton).fixedSize()
            }
            .padding(4)
        }
    }
}

#Preview("A cloud-read line whose shape changed") {
    let _ = SegmentRereadState.shared.markStale(["line-1"])
    StaleReadingBar(segmentId: "line-1").frame(width: 360)
}

#Preview("A re-read that could not be queued") {
    let _ = SegmentRereadState.shared.markFailed(["line-2"], "No reading model is set up")
    StaleReadingBar(segmentId: "line-2").frame(width: 360)
}
