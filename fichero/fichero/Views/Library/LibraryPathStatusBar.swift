import SwiftUI

// MARK: - Finder-style path bar + status bar for the LIBRARY pane
// (Daniel #106-108, 2026-08-09: "we want the status bar just on the library…
// we need a path bar down there that has icons with chevrons and we need a
// status bar telling us what is shown or selected.") The old window-wide
// detailStatusPathBar spanned library + preview + reader; these two rows
// live in LibraryView's bottom inset so they scope to the pane exactly.

/// Finder's status grammar: "5 items" / "2 of 5 selected".
/// File scope so Swift Testing calls it off-main.
func libraryStatusText(selectionCount: Int, itemCount: Int) -> String {
    if selectionCount > 0 {
        return "\(selectionCount) of \(itemCount) selected"
    }
    return itemCount == 1 ? "1 item" : "\(itemCount) items"
}

/// Ancestry for the path bar: the anchor document first resolved, then its
/// parent chain walked through `resolve`, root-first. Capped so a cyclic or
/// absurdly deep chain can't hang the bar.
func libraryPathCrumbs(
    anchorId: String?,
    resolve: (String) -> Document?
) -> [Document] {
    guard let anchorId, let anchor = resolve(anchorId) else { return [] }
    var crumbs: [Document] = [anchor]
    var cursor = anchor
    var hops = 0
    while hops < 8, let parentId = cursor.parentId, let parent = resolve(parentId) {
        // Cycle guard: a bad parent chain must not loop forever.
        guard !crumbs.contains(where: { $0.id == parent.id }) else { break }
        crumbs.insert(parent, at: 0)
        cursor = parent
        hops += 1
    }
    return crumbs
}

struct LibraryPathStatusBar: View {
    let crumbs: [Document]
    let statusText: String
    var onNavigate: (Document) -> Void = { _ in }

    var body: some View {
        VStack(spacing: 0) {
            if !crumbs.isEmpty {
                Divider()
                pathRow
            }
            Divider()
            statusRow
        }
        .background(.bar)
    }

    /// Finder's path bar: icon + name per crumb, chevron separators; every
    /// crumb navigates. Trailing crumb is the current location, inert.
    private var pathRow: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 4) {
                ForEach(Array(crumbs.enumerated()), id: \.element.id) { entry in
                    if entry.offset > 0 {
                        Image(systemName: "chevron.right")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(.tertiary)
                    }
                    crumbView(entry.element, isLast: entry.offset == crumbs.count - 1)
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 10)
        }
        .frame(height: 22)
        .accessibilityIdentifier("libraryPathBar")
    }

    @ViewBuilder
    private func crumbView(_ doc: Document, isLast: Bool) -> some View {
        let label = HStack(spacing: 4) {
            Image(systemName: doc.displaySymbol())
                .symbolVariant(doc.docType == .folder ? .fill : .none)
                .foregroundStyle(doc.docType == .folder ? Color.accentColor : Color.secondary)
            Text(DocumentTitle.displayName(for: doc))
                .lineLimit(1)
                .truncationMode(.middle)
        }
        .font(.caption)

        if isLast {
            label.foregroundStyle(.primary)
        } else {
            Button {
                onNavigate(doc)
            } label: {
                label
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .help("Go to \(DocumentTitle.displayName(for: doc))")
        }
    }

    /// Finder's status line: centered, quiet.
    private var statusRow: some View {
        Text(statusText)
            .font(.caption)
            .foregroundStyle(.secondary)
            .lineLimit(1)
            .frame(maxWidth: .infinity)
            .frame(height: 20)
            .accessibilityIdentifier("libraryStatusBar")
    }
}
