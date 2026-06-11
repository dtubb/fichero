import SwiftUI

/// A native `List(selection:)` of notes.
struct NoteListView: View {
    let notes: [NoteSelectionItem]

    @Bindable var focused: FocusedNote

    var onOpenInWindow: (() -> Void)?

    private var sortedNotes: [NoteSelectionItem] {
        notes.sorted { lhs, rhs in
            let lhsDate = lhs.note.updatedAt ?? lhs.note.createdAt ?? .distantPast
            let rhsDate = rhs.note.updatedAt ?? rhs.note.createdAt ?? .distantPast
            return lhsDate > rhsDate
        }
    }

    var body: some View {
        List(selection: $focused.id) {
            ForEach(sortedNotes) { item in
                row(for: item)
                    .tag(item.id)
                    .contextMenu {
                        if let onOpenInWindow {
                            Button("Open in Window") {
                                focused.select(item.id, in: notes)
                                onOpenInWindow()
                            }
                        }
                    }
            }
        }
        .listStyle(.inset)
        .overlay {
            if notes.isEmpty {
                emptyState
            }
        }
        .onChange(of: focused.id) { _, _ in
            if focused.id == nil {
                focused.clear()
            } else {
                focused.resolve(in: notes)
            }
        }
        .onChange(of: notes) { _, items in
            focused.resolve(in: items)
        }
    }

    @ViewBuilder
    private func row(for item: NoteSelectionItem) -> some View {
        NoteRow(item: item)
    }

    @ViewBuilder
    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "note.text")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No notes")
                .font(.callout)
            Text("Add a note, or adjust the filters.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .padding(.horizontal, 16)
    }
}

private struct NoteRow: View {
    let item: NoteSelectionItem

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: kindIcon)
                .foregroundStyle(.secondary)
                .frame(width: 18)
            VStack(alignment: .leading, spacing: 3) {
                Text(item.title)
                    .font(.body)
                    .lineLimit(2)
                Text(item.bodyPreview)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
                if let metadata = metadataLine {
                    Text(metadata)
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                        .lineLimit(1)
                }
            }
            Spacer(minLength: 0)
            if let updatedLabel = item.updatedLabel {
                Text(updatedLabel)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.vertical, 2)
    }

    private var metadataLine: String? {
        var parts: [String] = [item.kindLabel]
        if let scopeLabel = item.scopeLabel { parts.append(scopeLabel) }
        if let tags = item.tagsLabel { parts.append(tags) }
        return parts.joined(separator: " · ")
    }

    private var kindIcon: String {
        switch item.note.kind?.rawValue {
        case "reference":
            return "quote.bubble"
        case "hub":
            return "network"
        case "inbox":
            return "tray"
        case "fleeting":
            return "sparkles"
        case "permanent":
            return "bookmark"
        default:
            return "note.text"
        }
    }
}
