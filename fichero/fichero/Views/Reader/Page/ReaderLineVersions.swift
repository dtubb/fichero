import SwiftUI
#if os(macOS)
import AppKit
#endif

/// A line's versions under its disclosure triangle (`source.editor.reader-line-discloses-its-versions`, #6492): each
/// reading says who made it, what it is and when; one made from or correcting another sits under it. Reading only;
/// choosing which counts stays in the Inspector.
struct ReaderLineVersions: View {
    let roots: [ReadingTree]
    /// The reading that counts, checked.
    let countingId: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Self.flattened(roots)) { row in
                versionRow(row.tree.reading).padding(.leading, CGFloat(row.depth) * 16)
            }
        }
    }

    private func versionRow(_ reading: InspectorText.Reading) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Image(systemName: reading.id == countingId ? "checkmark" : "circle.fill")
                .font(reading.id == countingId ? .caption : .system(.caption2).weight(.ultraLight))
                .foregroundStyle(reading.id == countingId ? AnyShapeStyle(Color.accentColor) : AnyShapeStyle(.tertiary))
                .accessibilityLabel(reading.id == countingId ? "Counts" : "")
            VStack(alignment: .leading, spacing: 1) {
                Text(reading.content).font(.callout).textSelection(.enabled)
                Text(Self.caption(reading)).font(.caption).foregroundStyle(.secondary)
            }
        }
    }

    /// "Transcription, modernised · gemini-3-flash via OpenRouter · 2 days ago".
    static func caption(_ reading: InspectorText.Reading) -> String {
        let what = ([reading.kind] + [reading.level].compactMap { $0 })
            .map { $0.replacingOccurrences(of: "_", with: " ") }
            .joined(separator: ", ")
        let who = reading.whoRead ?? reading.author ?? reading.maker
        let when = reading.createdAt.map { $0.formatted(.relative(presentation: .named)) }
        return ([what.prefix(1).uppercased() + what.dropFirst(), who] + [when].compactMap { $0 }).joined(separator: " · ")
    }

    struct Row: Identifiable {
        let tree: ReadingTree
        let depth: Int
        var id: String { tree.id }
    }

    /// Depth-first, so the rows read top to bottom as the tree does.
    static func flattened(_ roots: [ReadingTree], depth: Int = 0) -> [Row] {
        roots.flatMap { [Row(tree: $0, depth: depth)] + flattened($0.children, depth: depth + 1) }
    }
}

/// The triangle that opens a line's versions. A click opens this line; ⌥-click opens or closes every line.
struct ReaderVersionsTriangle: View {
    @Binding var own: (open: Bool, stamp: Int)?
    let count: Int

    @Environment(WindowState.self) private var windowState: WindowState?

    var isOpen: Bool { Self.isOpen(own: own, allOpen: windowState?.readerVersionsAllOpen ?? false,
                                   stamp: windowState?.readerVersionsStamp ?? 0) }

    /// A row's own click counts until the next ⌥-click.
    static func isOpen(own: (open: Bool, stamp: Int)?, allOpen: Bool, stamp: Int) -> Bool {
        if let own, own.stamp == stamp { return own.open }
        return allOpen
    }

    var body: some View {
        Button {
            let stamp = windowState?.readerVersionsStamp ?? 0
            if Self.optionHeld, let windowState {
                windowState.readerVersionsAllOpen = !isOpen
                windowState.readerVersionsStamp += 1
            } else {
                withAnimation(.snappy(duration: 0.16)) { own = (!isOpen, stamp) }
            }
        } label: {
            Label("\(count) Versions", systemImage: "chevron.right")
                .labelStyle(.iconOnly)
                .rotationEffect(.degrees(isOpen ? 90 : 0))
                .font(.caption)
                .foregroundStyle(.secondary)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .help(isOpen ? "Hide this line's versions (⌥-click: every line)" : "Show this line's \(count) versions (⌥-click: every line)")
        .accessibilityLabel(isOpen ? "Hide \(count) versions" : "Show \(count) versions")
    }

    private static var optionHeld: Bool {
        #if os(macOS)
        NSEvent.modifierFlags.contains(.option)
        #else
        false
        #endif
    }
}
