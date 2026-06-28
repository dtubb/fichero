import SwiftUI

/// Renders Markdown as native SwiftUI views — headings, lists, blockquotes,
/// fenced code blocks, and inline syntax (bold/italic/inline code/links).
///
/// SwiftUI's `Text(AttributedString(markdown:))` only renders *inline* syntax;
/// block structure collapses. This view splits the source into blocks and gives
/// each the right semantic treatment, using `AttributedString` for inline runs
/// within a block. Dependency-free; heavier Markdown (tables, images) is left as
/// raw inline text for now, matching `MarkdownCanvas` (#2264).
///
/// Reused by the chat bubbles (#2639). Semantic system fonts throughout so it
/// scales with the system text size.
struct MarkdownText: View {
    let text: String

    init(_ text: String) {
        self.text = text
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(MarkdownBlock.parse(text).enumerated()), id: \.offset) { _, block in
                blockView(block)
            }
        }
    }

    @ViewBuilder
    private func blockView(_ block: MarkdownBlock) -> some View {
        switch block {
        case .heading(let level, let content):
            inlineText(content)
                .font(headingFont(level))
                .fontWeight(.semibold)
        case .paragraph(let content):
            inlineText(content)
        case .blockquote(let content):
            HStack(alignment: .top, spacing: 8) {
                Rectangle()
                    .fill(.secondary)
                    .frame(width: 3)
                inlineText(content)
                    .foregroundStyle(.secondary)
            }
        case .codeBlock(let code):
            Text(code)
                .font(.callout.monospaced())
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(8)
                .background(Color(.textBackgroundColor).opacity(0.5))
                .clipShape(RoundedRectangle(cornerRadius: 6))
        case .list(let items):
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .top, spacing: 6) {
                        Text(item.marker)
                            .font(.body)
                            .monospacedDigit()
                        inlineText(item.content)
                    }
                }
            }
        }
    }

    /// Inline Markdown (bold/italic/code/links) → `Text`, falling back to the
    /// raw line if it doesn't parse.
    private func inlineText(_ line: String) -> Text {
        if let attributed = try? AttributedString(
            markdown: line,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        ) {
            return Text(attributed)
        }
        return Text(line)
    }

    private func headingFont(_ level: Int) -> Font {
        switch level {
        case 1: .title
        case 2: .title2
        case 3: .title3
        default: .headline
        }
    }
}

/// One parsed Markdown block. Parsing is line-based and intentionally small —
/// it covers the elements #2639 lists, not the full CommonMark grammar.
enum MarkdownBlock {
    case heading(level: Int, content: String)
    case paragraph(String)
    case blockquote(String)
    case codeBlock(String)
    case list([ListItem])

    struct ListItem {
        let marker: String
        let content: String
    }

    static func parse(_ text: String) -> [MarkdownBlock] {
        var blocks: [MarkdownBlock] = []
        let lines = text.components(separatedBy: "\n")
        var index = 0

        while index < lines.count {
            let trimmed = lines[index].trimmingCharacters(in: .whitespaces)

            if trimmed.isEmpty {
                index += 1
            } else if trimmed.hasPrefix("```") {
                (blocks, index) = consumeCodeBlock(lines, from: index, into: blocks)
            } else if let heading = headingBlock(trimmed) {
                blocks.append(heading)
                index += 1
            } else if trimmed.hasPrefix(">") {
                (blocks, index) = consumeBlockquote(lines, from: index, into: blocks)
            } else if listMarker(trimmed) != nil {
                (blocks, index) = consumeList(lines, from: index, into: blocks)
            } else {
                (blocks, index) = consumeParagraph(lines, from: index, into: blocks)
            }
        }

        return blocks
    }

    /// True for any line that starts a new block (ends an open paragraph).
    private static func isStructural(_ trimmed: String) -> Bool {
        trimmed.isEmpty || trimmed.hasPrefix("```") || trimmed.hasPrefix(">")
            || headingBlock(trimmed) != nil || listMarker(trimmed) != nil
    }

    private static func consumeCodeBlock(
        _ lines: [String], from start: Int, into blocks: [MarkdownBlock]
    ) -> ([MarkdownBlock], Int) {
        var code: [String] = []
        var index = start + 1
        while index < lines.count,
              !lines[index].trimmingCharacters(in: .whitespaces).hasPrefix("```") {
            code.append(lines[index])
            index += 1
        }
        return (blocks + [.codeBlock(code.joined(separator: "\n"))], index + 1)
    }

    private static func consumeBlockquote(
        _ lines: [String], from start: Int, into blocks: [MarkdownBlock]
    ) -> ([MarkdownBlock], Int) {
        var quote: [String] = []
        var index = start
        while index < lines.count {
            let line = lines[index].trimmingCharacters(in: .whitespaces)
            guard line.hasPrefix(">") else { break }
            quote.append(String(line.dropFirst()).trimmingCharacters(in: .whitespaces))
            index += 1
        }
        return (blocks + [.blockquote(quote.joined(separator: "\n"))], index)
    }

    private static func consumeList(
        _ lines: [String], from start: Int, into blocks: [MarkdownBlock]
    ) -> ([MarkdownBlock], Int) {
        var items: [ListItem] = []
        var index = start
        while index < lines.count,
              let item = listMarker(lines[index].trimmingCharacters(in: .whitespaces)) {
            items.append(item)
            index += 1
        }
        return (blocks + [.list(items)], index)
    }

    private static func consumeParagraph(
        _ lines: [String], from start: Int, into blocks: [MarkdownBlock]
    ) -> ([MarkdownBlock], Int) {
        var para: [String] = []
        var index = start
        while index < lines.count {
            let line = lines[index].trimmingCharacters(in: .whitespaces)
            if isStructural(line) { break }
            para.append(line)
            index += 1
        }
        return (blocks + [.paragraph(para.joined(separator: " "))], index)
    }

    private static func headingBlock(_ trimmed: String) -> MarkdownBlock? {
        guard trimmed.hasPrefix("#") else { return nil }
        let hashes = trimmed.prefix { $0 == "#" }
        let level = hashes.count
        guard level <= 6 else { return nil }
        let rest = trimmed.dropFirst(level)
        guard rest.hasPrefix(" ") else { return nil }
        return .heading(level: level, content: rest.trimmingCharacters(in: .whitespaces))
    }

    private static func listMarker(_ trimmed: String) -> ListItem? {
        // Unordered: -, *, +
        for bullet in ["- ", "* ", "+ "] where trimmed.hasPrefix(bullet) {
            return ListItem(marker: "•", content: String(trimmed.dropFirst(2)))
        }
        // Ordered: digits followed by ". "
        let digits = trimmed.prefix { $0.isNumber }
        if !digits.isEmpty {
            let rest = trimmed.dropFirst(digits.count)
            if rest.hasPrefix(". ") {
                return ListItem(marker: "\(digits).", content: String(rest.dropFirst(2)))
            }
        }
        return nil
    }
}
