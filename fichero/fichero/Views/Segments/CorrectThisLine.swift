import FicheroAPIClient
import SwiftUI

/// Correct This Line (#5499, `source.reading.correct-a-line`): on a line, in the Reader's Lines mode and the
/// Segments list, type what it says and the engine's one verb records it as a person's reading
/// (`SegmentService.correctLine`, `POST /api/segments/{id}/correct`). The app sends the line, the words and the
/// reading the person saw; the engine works out the rest.
///
/// ponytail: the route answers with the reading, not an audit row, so this correction has no ⌘Z step yet; it
/// moves onto worker A's audited action (segment id plus text) when that lands, and gains ⌘Z there.
enum CorrectLine {
    /// Whether the verb is offered on a segment: a line, the level a reading of a line is.
    static func offers(_ segment: Segment?) -> Bool {
        segment?.kind.lowercased() == "line"
    }

    /// The words to send, or nil when there is nothing to correct: empty, or the same as what it reads now.
    static func text(_ typed: String, replacing current: String?) -> String? {
        let words = typed.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !words.isEmpty, words != (current ?? "").trimmingCharacters(in: .whitespacesAndNewlines) else { return nil }
        return words
    }
}

/// The menu item and the sheet that asks for the words. One per surface; `target` is the line being corrected.
struct CorrectThisLineModifier: ViewModifier {
    @Binding var target: Segment?

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @State private var words = ""
    @State private var reading: InspectorText.Reading?
    @State private var failure: String?

    func body(content: Content) -> some View {
        content
            .alert("Correct This Line", isPresented: Binding(get: { target != nil }, set: { if !$0 { target = nil } })) {
                TextField("Words", text: $words)
                    .font(BundledFonts.shared.font(.body))  // the bundled script fonts, as every line view (#5842)
                Button("Save") {
                    let line = target
                    Task { await save(line) }
                }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("What the line says, recorded as your reading.")
            }
            .alert("The line was not corrected", isPresented: Binding(get: { failure != nil }, set: { if !$0 { failure = nil } })) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(failure ?? "")
            }
            .task(id: target?.id) {
                guard let target else { return }
                words = target.text ?? ""
                reading = try? await segmentService?.readings(segmentId: target.id)?.countingReading(ofKind: "transcription")
                if let shown = reading?.content { words = shown }
            }
    }

    private func save(_ line: Segment?) async {
        guard let line, let segmentService,
              let text = CorrectLine.text(words, replacing: reading?.content ?? line.text) else { return }
        do {
            _ = try await segmentService.correctLine(segmentId: line.id, text: text, expectedCountingId: reading?.id)
            await SegmentStore.shared(for: segmentService).load(documentId: line.documentId, force: true)
        } catch {
            failure = error.localizedDescription
        }
    }
}

extension View {
    /// Asks for a line's words while `target` is set, and sends them (`CorrectThisLineModifier`).
    func correctThisLine(_ target: Binding<Segment?>) -> some View {
        modifier(CorrectThisLineModifier(target: target))
    }
}

/// The verb on a row's own menu, on a line only: Page › Segments' own item (`CorrectLineMenuItem`, #5652).
struct CorrectThisLineButton: View {
    let segment: Segment?
    let correct: (Segment) -> Void

    var body: some View {
        if let segment, CorrectLine.offers(segment) {
            CorrectLineMenuItem(target: LineVerbsTarget(segment: segment, correct: { correct(segment) }))
        }
    }
}

#if DEBUG
#Preview("Correct This Line on a line's menu") {
    let anchor = SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "p1"))
    let line = Segment(
        id: "l1", provisional: false, documentId: "p1", passId: "p", kind: "line", kindRaw: nil,
        parentSegmentId: nil, provenanceKind: .externalImport, anchor: anchor, baseline: nil,
        text: "enel tþo q́ el escriuio", confidence: nil, sourceArtifactId: nil, boxIndex: 0, pageIndex: nil, metadata: nil
    )
    return Text(line.text ?? "")
        .font(BundledFonts.shared.font(.body))
        .padding()
        .contextMenu { CorrectThisLineButton(segment: line) { _ in } }
}
#endif
