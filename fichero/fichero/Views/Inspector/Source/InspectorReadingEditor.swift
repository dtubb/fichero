import SwiftUI

/// The Inspector's Edit… (#5201): the counting reading, edited in place and saved as a correction of it.
/// The Inspector twin of typing in the Reader -- the SAME message (`ReaderTextEdit.Message.edited`,
/// `basedOn` the reading shown) through the SAME runner (`ReaderTextEditRunner`), so the same
/// `representation.create`, the same stale check (another reading counts now: nothing is written) and ⌘Z.
enum InspectorReadingEdit {
    /// How the field lays out, from the segment's resolved direction (the engine's cascade).
    enum Layout: Equatable {
        case horizontal(rightToLeft: Bool)
        case vertical
    }

    static func layout(direction: String?) -> Layout {
        switch direction {
        case "ttb", "btt": .vertical
        case "rtl": .horizontal(rightToLeft: true)
        default: .horizontal(rightToLeft: false)
        }
    }

    /// The Reader's own message for a typed line: the new text, correcting the reading shown. A segment
    /// no reading counts for yet (`reading` nil) gets a first reading, correcting nothing.
    static func message(documentId: String, segmentId: String, text: String, editing reading: InspectorText.Reading?)
        -> ReaderTextEdit.Message {
        .edited(pageId: documentId, segmentId: segmentId, text: text, basedOn: reading?.id)
    }

    /// THE save of a person's typed reading of one segment: the Inspector's Edit… and the Reader's Lines
    /// row (#5414) both call it, so both are the Reader's `representation.create` through
    /// `ReaderTextEditRunner` -- the same stale check and ⌘Z. Unchanged words write nothing. Answers why
    /// nothing was written (`ReaderTextEditRunner.staleProblem` when another reading counts now), or nil.
    static func save(
        _ words: String, documentId: String, segmentId: String, editing reading: InspectorText.Reading?,
        runner: ReaderTextEditRunner
    ) async -> String? {
        let text = words.trimmingCharacters(in: .whitespacesAndNewlines)
        guard text != (reading?.content ?? "") else { return nil }
        let answer = await runner.apply(message(documentId: documentId, segmentId: segmentId, text: text, editing: reading))
        return answer?.problem
    }

    /// What the Inspector says when the edit did not land.
    static func note(for problem: String) -> String {
        problem == ReaderTextEditRunner.staleProblem
            ? "Another reading counts now, so yours was not saved. The Text shows what counts; edit it again."
            : "Not saved: \(problem)"
    }
}

/// The field itself, laid out in the segment's direction, with Save and Cancel.
struct InspectorReadingEditor: View {
    @Binding var text: String
    let layout: InspectorReadingEdit.Layout
    let save: () -> Void
    let cancel: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            field
            HStack {
                Spacer()
                Button("Cancel", role: .cancel, action: cancel).keyboardShortcut(.cancelAction)
                Button("Save", action: save).keyboardShortcut(.defaultAction)
            }
            .font(.caption)
        }
    }

    @ViewBuilder
    private var field: some View {
        switch layout {
        case .vertical:
            #if os(macOS)
            VerticalTextEditor(text: $text)
                .frame(minWidth: 60, maxWidth: .infinity, minHeight: 180)
                .accessibilityLabel("Reading, top to bottom")
            #else
            horizontalField(rightToLeft: false)
            #endif
        case .horizontal(let rightToLeft):
            horizontalField(rightToLeft: rightToLeft)
        }
    }

    private func horizontalField(rightToLeft: Bool) -> some View {
        TextField("Reading", text: $text, axis: .vertical)
            .font(BundledFonts.shared.font(.body))
            .multilineTextAlignment(rightToLeft ? .trailing : .leading)
            .environment(\.layoutDirection, rightToLeft ? .rightToLeft : .leftToRight)
            .textFieldStyle(.roundedBorder)
            .lineLimit(1...6)
    }
}

#if os(macOS)
/// A text editor whose lines run top to bottom (vertical Han, Mongolian): AppKit's vertical layout
/// orientation, which SwiftUI's fields do not offer.
struct VerticalTextEditor: NSViewRepresentable {
    @Binding var text: String
    /// The words' point size; 0 is the body style's own. The Reader's Lines mode zooms it (#5414).
    var pointSize: CGFloat = 0

    func makeNSView(context: Context) -> NSScrollView {
        let scroll = NSTextView.scrollableTextView()
        guard let view = scroll.documentView as? NSTextView else { return scroll }
        view.delegate = context.coordinator
        view.isRichText = false
        view.font = font
        view.setLayoutOrientation(.vertical)
        view.string = text
        return scroll
    }

    func updateNSView(_ scroll: NSScrollView, context: Context) {
        guard let view = scroll.documentView as? NSTextView else { return }
        if view.font?.pointSize != font.pointSize { view.font = font }
        if view.string != text { view.string = text }
    }

    /// The engine's bundled faces after the system's, as every reading in the app (#5210).
    private var font: NSFont {
        BundledFonts.ctFont(
            base: BundledFonts.systemDescriptor(.body), size: pointSize, cascade: BundledFonts.shared.cascade
        ) as NSFont
    }

    func makeCoordinator() -> Coordinator { Coordinator(text: $text) }

    final class Coordinator: NSObject, NSTextViewDelegate {
        let text: Binding<String>
        init(text: Binding<String>) { self.text = text }
        func textDidChange(_ notification: Notification) {
            if let view = notification.object as? NSTextView { text.wrappedValue = view.string }
        }
    }
}
#endif

#if DEBUG
#Preview("Edit…: right to left, and top to bottom") {
    @Previewable @State var syriac = "ܒܪܫܝܬ ܐܝܬܘܗܝ ܗܘܐ ܡܠܬܐ"
    @Previewable @State var chinese = "登庸九年"
    VStack(alignment: .leading, spacing: 16) {
        InspectorReadingEditor(text: $syriac, layout: .horizontal(rightToLeft: true), save: {}, cancel: {})
        InspectorReadingEditor(text: $chinese, layout: .vertical, save: {}, cancel: {})
    }
    .padding()
    .frame(width: 300)
}
#endif
