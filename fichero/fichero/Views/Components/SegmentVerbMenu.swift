import SwiftUI

/// The segment verbs beyond Correct, Show and Delete, as ONE menu body for every surface that lists lines
/// (`source.editor.segment-verbs-are-the-same-everywhere`, Step 1.25): the Order list's row menu and the Reader's line
/// menu both mount it, so no surface has a verb another lacks. A verb that cannot apply to `ids` is absent, never greyed.
/// Each is the one audited call (`SegmentMover`, `SegmentEdit`), one ⌘Z.
struct SegmentVerbMenu: View {
    /// The segments the verb means: the row, or the selection when it holds the row (`SegmentDeleter.ids`).
    let ids: [String]
    let documentId: String
    /// Why a verb did nothing, or nil when it was sent; the host says it under its list.
    var onNote: (String?) -> Void = { _ in }

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(WindowSteps.self) private var windowSteps: WindowSteps?

    var body: some View {
        let segments = store?.workingSegments(documentId: documentId) ?? []
        let targets = SegmentMover.targets(for: ids, in: segments)
        if let first = targets.first {
            // What the selection can go into is one level coarser than it: a line into a region, a word into a line, a
            // letter into a word. Named by kind and by place among that kind on the page, as the lists name them.
            let noun = InspectorPath.name(of: first)
            Menu("Move Into \(noun)") {
                ForEach(targets, id: \.id) { target in
                    let position = (segments.filter { $0.kind == target.kind }.firstIndex { $0.id == target.id } ?? 0) + 1
                    Button("\(noun) \(position)") { move(into: target.id) }
                }
            }
        }
        if SegmentMover.canLift(ids, in: segments) {
            let byId = Dictionary(segments.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
            let parent = ids.lazy.compactMap { byId[$0]?.parentSegmentId }.compactMap { byId[$0] }.first
            Button("Lift Out of \(parent.map(InspectorPath.name(of:)) ?? "Region")") { move(into: nil) }
        }
        if ids.count >= 2 {
            Button("Join") { run("Join Lines") { SegmentEdit.join($0) } }
        }
        if !ids.isEmpty {
            Divider()
            SegmentAttributeMenu.Items(apply: { attribute in
                run("Set Segment") { SegmentEdit.set(attribute, on: $0) }
            })
        }
    }

    private var store: SegmentStore? { segmentService.map { SegmentStore.shared(for: $0) } }

    private func move(into parent: String?) {
        guard let store else { return }
        let segments = SegmentDeleter.segments(ids, documentId: documentId, store: store)
        let actionsService = actionStore?.actionsService, steps = windowSteps, documentId = documentId
        let note = onNote
        Task {
            note(await SegmentMover.run(
                segments, into: parent, documentId: documentId, store: store, actionsService: actionsService, steps: steps
            ))
        }
    }

    private func run(
        _ actionName: String, plan: @escaping ([Segment]) -> Result<SegmentEdit.Call, SegmentEdit.Refusal>
    ) {
        guard let store, let actionsService = actionStore?.actionsService else { return }
        let segments = SegmentDeleter.segments(ids, documentId: documentId, store: store)
        let steps = windowSteps, documentId = documentId
        let note = onNote
        Task {
            switch plan(segments) {
            case .failure(let refusal): note(SegmentMover.problem(refusal))
            case .success(let call):
                do {
                    try await SegmentEditRunner(actionsService: actionsService, store: store).run(
                        call, documentId: documentId, actionName: actionName, steps: steps
                    )
                    note(nil)
                } catch { note("That did not happen: \(error.localizedDescription)") }
            }
        }
    }
}

#if DEBUG
#Preview("Two lines picked: Join and the attributes (Move Into / Lift Out need a page's segments)") {
    Menu("Line 2") {
        SegmentVerbMenu(ids: ["line-1", "line-2"], documentId: "page-1")
    }
    .padding()
    .frame(width: 240)
}
#endif
