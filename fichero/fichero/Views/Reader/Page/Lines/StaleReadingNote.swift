import SwiftUI

/// Under a line whose shape changed after a paid cloud model read it: the words may be out of date, and reading again is
/// the person's call (it costs). Also says so when a re-read could not be queued (`segment-actions.automatic-rerun-after-an-edit`).
struct StaleReadingNote: View {
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
