import SwiftUI

/// A gathered set in the Segments pane (#4942): everything in one hand, every instance of a sign,
/// across pages. Each row opens its page in the Preview with the segment selected; what the engine
/// left out because this reader may not read those pages is said beneath the list (#5180).
struct SegmentsGatheredList: View {
    let gather: SegmentsGather
    /// Opens a row's page (the pane reveals it in the Library and selects the segment on arrival).
    let open: (SegmentsGathered.Row) -> Void

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(\.undoManager) private var undoManager
    @State private var answer = SegmentsGathered.Answer()
    @State private var loading = true

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if answer.rows.isEmpty, !loading {
                ContentUnavailableView(
                    "Nothing Gathered", systemImage: "square.stack",
                    description: Text(SegmentsGathered.withheldNote(answer.withheld) ?? "No segment is in this set yet.")
                )
            } else {
                List(answer.rows) { row in
                    HStack(alignment: .firstTextBaseline) {
                        Button { open(row) } label: {
                            VStack(alignment: .leading, spacing: 1) {
                                Text(row.title).lineLimit(2)
                                Text(row.detail).font(.caption).foregroundStyle(.secondary)
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .buttonStyle(.plain)
                        .disabled(row.documentId == nil)
                        .help(row.documentId == nil ? "This segment could not be read" : "Open its page with the segment selected")
                        if let matchId = row.matchId {
                            // Reviewing a proposal (#5165): the audited verbs, ⌘Z by their own audit ids.
                            Button("Accept") { Task { await review("segment.match_accept", matchId, "Accept Match") } }
                            Button("Reject") { Task { await review("segment.match_reject", matchId, "Reject Match") } }
                        }
                    }
                    .buttonStyle(.borderless)
                }
                if let note = SegmentsGathered.withheldNote(answer.withheld) {
                    Divider()
                    Text(note).font(.caption).foregroundStyle(.secondary).padding(8)
                }
            }
        }
        .task(id: gather.title) { await reload() }
    }

    private func reload() async {
        loading = true
        defer { loading = false }
        guard let segmentService else { return }
        answer = await Self.load(gather, segmentService: segmentService)
    }

    /// Accept or reject one proposed match, then re-read the set (a reviewed match leaves it).
    private func review(_ action: String, _ matchId: String, _ actionName: String) async {
        guard let actionsService = actionStore?.actionsService else { return }
        try? await AuditedAction.run(
            action, params: SegmentMatchIdRequest(matchId: matchId), actionName: actionName,
            actionsService: actionsService, undoManager: undoManager, afterChange: { await reload() }
        )
    }

    /// The set, with each segment read so its row can say what it is and which page opens.
    /// ponytail: one segment read per attribution (a hand has no page to batch by); a batch route if
    /// hands grow to thousands of lines.
    @MainActor
    static func load(_ gather: SegmentsGather, segmentService: SegmentService) async -> SegmentsGathered.Answer {
        switch gather {
        case .hand(let id, _):
            guard let found = try? await HandService(client: segmentService.client).everything(handId: id) else {
                return SegmentsGathered.Answer()
            }
            var segments: [String: Segment] = [:]
            for segmentId in Set(found.attributions.compactMap(\.segmentId)) {
                if let segment = try? await segmentService.segment(id: segmentId) { segments[segmentId] = segment }
            }
            return SegmentsGathered.Answer(
                rows: SegmentsGathered.handRows(found.attributions, segments: segments), withheld: found.withheld
            )
        case .sign(let id, _):
            guard let found = try? await SignService(client: segmentService.client).instances(signId: id) else {
                return SegmentsGathered.Answer()
            }
            let store = SegmentStore.shared(for: segmentService)
            var segments: [String: Segment] = [:]
            for documentId in Set(found.uses.map(\.documentId)) {
                await store.load(documentId: documentId)
                for segment in store.segments(documentId: documentId) { segments[segment.id] = segment }
            }
            return SegmentsGathered.Answer(rows: SegmentsGathered.signRows(found.uses, segments: segments), withheld: found.withheld)
        case .matches(let documentId):
            guard let found = try? await segmentService.proposedMatches(documentId: documentId) else {
                return SegmentsGathered.Answer()
            }
            let store = SegmentStore.shared(for: segmentService)
            await store.load(documentId: documentId)
            let segments = Dictionary(
                store.segments(documentId: documentId).map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first }
            )
            return SegmentsGathered.Answer(rows: SegmentsGathered.matchRows(found, documentId: documentId, segments: segments))
        }
    }
}

#if DEBUG
/// The rows as the pane lists them: everything in hand B across two pages, one line only 60% sure,
/// and one more on a page this reader may not read, said beneath.
#Preview("Gathered: everything in hand B") {
    let answer = SegmentsGathered.Answer(rows: [
        .init(id: "a1", segmentId: "l1", documentId: "p1", title: "Line · ܐܒܪܗܡ ܐܘܠܕ ܠܐܝܣܚܩ", detail: "judged by owner · sure 80%"),
        .init(id: "a2", segmentId: "l2", documentId: "p2", title: "Line · ܐܝܣܚܩ ܐܘܠܕ ܠܝܥܩܘܒ", detail: "judged by owner · sure 60%")
    ], withheld: 1)
    VStack(alignment: .leading, spacing: 0) {
        List(answer.rows) { row in
            VStack(alignment: .leading, spacing: 1) {
                Text(row.title)
                Text(row.detail).font(.caption).foregroundStyle(.secondary)
            }
        }
        if let note = SegmentsGathered.withheldNote(answer.withheld) {
            Text(note).font(.caption).foregroundStyle(.secondary).padding(8)
        }
    }
    .frame(width: 320, height: 240)
}
#endif
