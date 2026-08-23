import SwiftUI

// MARK: - Finder-style path bar + status bar for the LIBRARY pane
// (Daniel #106-108, 2026-08-09: "we want the status bar just on the library…
// we need a path bar down there that has icons with chevrons and we need a
// status bar telling us what is shown or selected.") The old window-wide
// detailStatusPathBar spanned library + preview + reader; these two rows
// live in LibraryView's bottom inset so they scope to the pane exactly.

/// What a DATA view's selection looks like to the status line — reported up
/// by DatasetModeView so the pane's bottom row speaks the dataset's language
/// instead of the browser's ("1 of 63 selected" over a cards pane of 160
/// dated entries, 2026-08-16).
struct DatasetSelectionStatus: Equatable {
    var count: Int
    var total: Int
    var noun: String
    var detail: String?
}

/// Finder's status grammar: "5 items" / "2 of 5 selected" — and in the data
/// views, the DATASET's language (Daniel 2026-08-16: "its 1 of X dates
/// selected or something at the very bottom. make it clearer"): the noun
/// names what the rows ARE ("1 of 160 dates selected"), and a single
/// selection appends its identity ("… — January 14, 1918").
/// File scope so Swift Testing calls it off-main.
func libraryStatusText(
    selectionCount: Int,
    itemCount: Int,
    noun: String? = nil,
    detail: String? = nil
) -> String {
    let single = noun ?? "item"
    // "entries", not "entrys" (Daniel's screenshot, 2026-08-23). English
    // plurals for the handful of nouns the status line actually names.
    let plural = single.hasSuffix("y") && !single.hasSuffix("ey")
        ? String(single.dropLast()) + "ies"
        : single + "s"
    if selectionCount > 0 {
        let counted = noun.map { _ in "\(selectionCount) of \(itemCount) \(plural) selected" }
            ?? "\(selectionCount) of \(itemCount) selected"
        if let detail, selectionCount == 1 {
            return "\(counted) — \(detail)"
        }
        return counted
    }
    return itemCount == 1 ? "1 \(single)" : "\(itemCount) \(plural)"
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

struct LibraryPathStatusBar<CrumbMenu: View>: View {
    let crumbs: [Document]
    let statusText: String
    var onNavigate: (Document) -> Void = { _ in }
    /// Crumbs double as drag SOURCES (#4591, Daniel: "click on one of the
    /// folders to go there, or drag and drop it somewhere") — the host
    /// supplies the same payload its rows use; nil keeps a crumb inert.
    var dragPayload: (Document) -> LibraryItemDrag? = { _ in nil }
    /// Right-click menu for a crumb (#4591): the host passes the SAME
    /// document context menu its rows use; EmptyView keeps crumbs menu-less.
    @ViewBuilder var crumbMenu: (Document) -> CrumbMenu

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
            crumbDraggable(label.foregroundStyle(.primary), doc)
        } else {
            crumbDraggable(
                Button {
                    onNavigate(doc)
                } label: {
                    label
                }
                .buttonStyle(.plain)
                .foregroundStyle(.secondary)
                .help("Go to \(DocumentTitle.displayName(for: doc))"),
                doc
            )
        }
    }

    /// A crumb with the row drag payload attached when the host offers one —
    /// so a path-bar folder drags exactly like its library row (#4591).
    @ViewBuilder
    private func crumbDraggable(_ view: some View, _ doc: Document) -> some View {
        // Menu built at OPEN, not per render (#4544 pattern).
        let withMenu = view.contextMenu { SidebarDeferredMenuContent { crumbMenu(doc) } }
        if let payload = dragPayload(doc) {
            withMenu.draggable(payload) {
                RowDragPreview(name: doc.name, systemImage: doc.displaySymbol())
            }
        } else {
            withMenu
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
