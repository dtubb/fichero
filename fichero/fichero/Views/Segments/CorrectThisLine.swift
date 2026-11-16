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

    /// A pinch's magnification applied to the picture's zoom, kept between the line's own size and six times it.
    static func zoomed(_ zoom: Double, by magnification: Double) -> Double {
        min(6, max(1, zoom * (1 + magnification)))
    }

    /// Records `words` as the person's reading of `line` and reloads the page's segments: the sheet's save, for a caller with no sheet.
    static func send(_ line: Segment, words: String, segmentService: SegmentService) async throws {
        let reading = try? await segmentService.readings(segmentId: line.id)?.countingReading(ofKind: "transcription")
        _ = try await segmentService.correctLine(segmentId: line.id, text: words, expectedCountingId: reading?.id)
        await SegmentStore.shared(for: segmentService).load(documentId: line.documentId, force: true)
    }
}

/// The menu item and the sheet that asks for the words. One per surface; `target` is the line being corrected.
struct CorrectThisLineModifier: ViewModifier {
    @Binding var target: Segment?

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @State private var words = ""
    @State private var reading: InspectorText.Reading?
    /// The line's picture, so the words are corrected against the ink (fetched as the Reader's row fetches it).
    @State private var picture: Data?
    @State private var failure: String?

    func body(content: Content) -> some View {
        content
            .sheet(isPresented: Binding(get: { target != nil }, set: { if !$0 { target = nil } })) {
                CorrectLineSheet(
                    words: $words, picture: picture,
                    save: { let line = target; target = nil; Task { await save(line) } },
                    cancel: { target = nil }
                )
            }
            .alert("The line was not corrected", isPresented: Binding(get: { failure != nil }, set: { if !$0 { failure = nil } })) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(failure ?? "")
            }
            .task(id: target?.id) {
                guard let target else { return }
                picture = nil
                words = target.text ?? ""
                if let segmentService {
                    picture = try? await SegmentPictureService(client: segmentService.client)
                        .picture(segmentId: target.id, size: ReaderLines.pictureSize)
                }
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

/// The sheet Correct This Line asks in: the line's picture (zoomed with the pinch, the buttons or ⌘+ / ⌘-, scrolled
/// when larger than the sheet) above the words, so a line is corrected against its ink, not from memory.
struct CorrectLineSheet: View {
    @Binding var words: String
    let picture: Data?
    let save: () -> Void
    let cancel: () -> Void

    @State private var zoom = 1.0
    @State private var pinchStart: Double?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Correct This Line").font(.headline)
            ScrollView([.horizontal, .vertical]) {
                if let picture, let image = PlatformImage(data: picture) {
                    Image(platformImage: image)
                        .resizable().scaledToFit()
                        .frame(width: 560 * zoom)
                        .accessibilityLabel("Picture of the line")
                } else {
                    Rectangle().fill(.quaternary).frame(width: 560, height: 60)
                        .overlay { Image(systemName: "photo").foregroundStyle(.secondary) }
                }
            }
            .frame(height: 200)
            .background(.quaternary.opacity(0.4), in: RoundedRectangle(cornerRadius: 6))
            .gesture(MagnifyGesture()
                .onChanged { value in
                    let start = pinchStart ?? zoom
                    pinchStart = start
                    zoom = CorrectLine.zoomed(start, by: value.magnification - 1)
                }
                .onEnded { _ in pinchStart = nil })
            HStack {
                Button { zoom = CorrectLine.zoomed(zoom, by: -0.25) } label: { Image(systemName: "minus.magnifyingglass") }
                    .keyboardShortcut("-", modifiers: .command)
                    .accessibilityLabel("Zoom out")
                Button { zoom = CorrectLine.zoomed(zoom, by: 0.25) } label: { Image(systemName: "plus.magnifyingglass") }
                    .keyboardShortcut("=", modifiers: .command)
                    .accessibilityLabel("Zoom in")
                Spacer()
            }
            .buttonStyle(.borderless)
            TextField("Words", text: $words)
                .font(BundledFonts.shared.font(.body))  // the bundled script fonts, as every line view (#5842)
                .onSubmit(save)
            Text("What the line says, recorded as your reading.").font(.caption).foregroundStyle(.secondary)
            HStack {
                Spacer()
                Button("Cancel", role: .cancel, action: cancel).keyboardShortcut(.cancelAction)
                Button("Save", action: save).keyboardShortcut(.defaultAction)
            }
        }
        .padding(16)
        .frame(minWidth: 600)
    }
}
