import SwiftUI

/// The mark that says "this picture is a group of pages" (#5570, `library.group.lists-as-a-container`):
/// the stack symbol and the page count, laid on the group's picture (its first page) in every list,
/// table and icon well. Without it a group read as one more photograph of a page.
struct GroupStackBadge: View {
    let pageCount: Int

    /// What the badge says, also its accessibility label. Pure so it is testable without a view.
    nonisolated static func label(pageCount: Int) -> String {
        pageCount == 1 ? "Group of 1 page" : "Group of \(pageCount) pages"
    }

    var body: some View {
        HStack(spacing: 2) {
            Image(systemName: DocType.group.icon)
            Text(pageCount, format: .number)
                .monospacedDigit()
        }
        .font(.caption2)
        .padding(.horizontal, 3)
        .padding(.vertical, 1)
        .background(.regularMaterial, in: Capsule())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Self.label(pageCount: pageCount))
        .allowsHitTesting(false)
    }
}

extension View {
    /// Lay the group mark on a group's picture; nothing for any other node.
    @ViewBuilder
    func groupStackBadge(for document: Document) -> some View {
        if document.isGroup {
            overlay(alignment: .bottomTrailing) {
                GroupStackBadge(pageCount: document.childCount)
                    .padding(2)
            }
        } else {
            self
        }
    }
}

#Preview("Group mark on a page") {
    RoundedRectangle(cornerRadius: 4)
        .fill(.quaternary)
        .frame(width: 84, height: 108)
        .groupStackBadge(for: Document(id: "g", docType: .group, name: "Sentencia 1", childCount: 12))
        .padding()
}
