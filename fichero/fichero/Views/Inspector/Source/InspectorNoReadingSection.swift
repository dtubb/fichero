import SwiftUI

/// The Inspector's Text section for a segment left WITHOUT a reading (`source.textedit.deleting-words-keeps-ink`;
/// `SegmentsPane.lacksReading`): it says so, and offers typing one -- the same `representation.create` a
/// line typed in the Reader makes, a person's reading, ⌘Z. Never hidden: what has no text is still ink.
struct InspectorNoReadingSection: View {
    let segmentId: String
    let documentId: String
    /// Re-read the Inspector's text once the reading is made or undone.
    let afterChange: @MainActor () async -> Void

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(\.undoManager) private var undoManager
    @State private var typing = false
    @State private var words = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Text").font(.headline)
            Text("No reading").font(.body).foregroundStyle(.secondary)
            Button("Type a Reading…") {
                words = ""
                typing = true
            }
            .buttonStyle(.borderless)
            .font(.caption)
            .help("Type what this segment says, as a person's reading")
        }
        .alert("Type a Reading", isPresented: $typing) {
            TextField("Words", text: $words)
            Button("Save") { Task { await save() } }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("A new reading of this segment, recorded as yours.")
        }
    }

    private func save() async {
        let content = words.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !content.isEmpty, let segmentService, let actionsService = actionStore?.actionsService else { return }
        let store = SegmentStore.shared(for: segmentService)
        let documentId = documentId
        let afterChange = afterChange
        try? await AuditedAction.run(
            "representation.create",
            params: NewReadingParams(
                documentId: documentId, segmentId: segmentId, kind: "transcription", content: content,
                correctsRepresentationId: nil
            ),
            actionName: "Type a Reading", actionsService: actionsService, undoManager: undoManager,
            afterChange: {
                await store.load(documentId: documentId, force: true)
                await afterChange()
            }
        )
    }
}

#if DEBUG
#Preview("A line with no reading yet") {
    InspectorNoReadingSection(segmentId: "s1", documentId: "p1", afterChange: {})
        .padding()
        .frame(width: 280)
}
#endif
