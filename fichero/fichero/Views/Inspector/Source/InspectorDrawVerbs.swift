import SwiftUI

/// The Inspector's drawing verbs on the selected segment (#7083): Add Line on a region, Add Word on a line (the polygon tool
/// armed at that level, the shape going into the segment it is drawn in), and Change Kind (region ↔ line, one
/// `segment.convert_level`, one ⌘Z).
struct InspectorDrawVerbs: View {
    let selected: [Segment]
    let documentId: String
    /// Why Change Kind did not happen, said by the host under its head; nil after one did.
    var onNote: (String?) -> Void = { _ in }

    @Environment(WindowState.self) private var windowState: WindowState?
    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(WindowSteps.self) private var windowSteps: WindowSteps?

    var body: some View {
        if let level = SegmentShapes.addLevel(for: selected) {
            Button(level == .word ? "Add Word" : "Add Line") { windowState?.armDraw(level) }
                .buttonStyle(.borderless)
                .font(.caption)
                .help("Draw a \(level.rawValue) inside the selected \(selected.first?.kind.lowercased() ?? "segment")")
        }
        if !selected.isEmpty, selected.allSatisfy({ SegmentShapes.changedKind(of: $0) != nil }) {
            Menu("Change Kind") {
                Button("Region") { change(to: "region") }
                Button("Line") { change(to: "line") }
            }
            .menuStyle(.button)
            .buttonStyle(.borderless)
            .fixedSize()
            .font(.caption)
            .help("Make the selection a region or a line")
        }
    }

    private func change(to kind: String) {
        guard let segmentService, let actionsService = actionStore?.actionsService else { return }
        let store = SegmentStore.shared(for: segmentService)
        let (documentId, steps, note, chosen) = (documentId, windowSteps, onNote, selected)
        Task {
            switch SegmentEdit.convertLevel(chosen, to: kind) {
            case .failure(let refusal): note(SegmentMover.problem(refusal))
            case .success(let call):
                do {
                    _ = try await SegmentEditRunner(actionsService: actionsService, store: store).run(
                        call, documentId: documentId, actionName: "Change Kind", steps: steps
                    )
                    note(nil)
                } catch { note("That did not happen: \(error.localizedDescription)") }
            }
        }
    }
}
