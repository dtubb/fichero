import SwiftUI

/// Renders a Markdown representation as scrollable, selectable text (#2264).
///
/// Native rendering only — `AttributedString(markdown:)` for inline + block
/// syntax, falling back to the raw text if it doesn't parse. Heavier Markdown
/// (tables, images) can graduate to a web view later if a corpus needs it.
struct MarkdownCanvas: View {
    let text: String

    private var attributed: AttributedString {
        (try? AttributedString(
            markdown: text,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        )) ?? AttributedString(text)
    }

    var body: some View {
        ScrollView {
            Text(attributed)
                .font(.body)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
                // Slim margin — more width for the text (Daniel, 2026-08-10).
                .padding(8)
        }
    }
}

#Preview {
    MarkdownCanvas(text: "A **bold** word, some *emphasis* and `code`.")
        .frame(width: 320, height: 160)
}
