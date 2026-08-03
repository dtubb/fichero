import SwiftUI

/// The shared N-up page-image grid for the reading surface (#2090 Tier 2).
///
/// Renders a document's ordered pages into an N-column `LazyVGrid` of
/// storage-backed `LibraryImageView`s — the one renderer that serves both the
/// PDF 3-up / 4-up modes (which exceed PDFKit's two-up ceiling) and image
/// page-sequences (which have no `PDFView` at all). `LazyVGrid` materializes and
/// recycles only the on-screen cells, so large documents stay smooth without a
/// hand-rolled recycler. Rendering goes through the storage HTTP endpoint via
/// `LibraryImageView` — never a local file path (the engine may be remote).
///
/// Single-click selects; double-click / the row action opens that page in the
/// existing reader (editing-is-navigation), matching the Finder-style selection
/// rule the rest of the app follows.
struct PageImageGrid: View {
    /// Ordered pages to lay out (a document's image/page siblings, in display order).
    let pages: [Document]
    /// Column count — driven by `PageLayoutMode.columns` (1…4).
    let columns: Int
    /// The currently-selected page id (single-click selection).
    @Binding var selectedID: String?
    /// Fires when a page is opened (double-click / Return) — the host navigates
    /// its single-page reader to this id rather than presenting a new editor.
    var onOpen: (String) -> Void

    /// Flexible, evenly-spaced columns. Clamped to at least one so a bad input
    /// can never produce an empty (crashing) grid configuration.
    static func gridColumns(count: Int, spacing: CGFloat = 12) -> [GridItem] {
        Array(repeating: GridItem(.flexible(), spacing: spacing), count: max(1, count))
    }

    var body: some View {
        ScrollView {
            LazyVGrid(columns: Self.gridColumns(count: columns), spacing: 12) {
                ForEach(pages) { page in
                    PageImageGridCell(
                        page: page,
                        isSelected: page.id == selectedID,
                        onSelect: { selectedID = page.id },
                        onOpen: { onOpen(page.id) }
                    )
                }
            }
            .padding(12)
        }
        .accessibilityIdentifier("pageImageGrid")
    }
}

/// One page cell: the storage-backed image, a selection ring, and the
/// select / open gestures. Extracted so the grid body stays declarative and the
/// per-cell state (hover, selection chrome) is localized.
private struct PageImageGridCell: View {
    let page: Document
    let isSelected: Bool
    let onSelect: () -> Void
    let onOpen: () -> Void

    var body: some View {
        // ★ EVERY FRAME PERFECT (#3617): reserve a stable page-shaped box up
        // front so the async `.display` image fits INSIDE it and the cell never
        // resizes — shifting the grid below — when its pixels arrive. Previously
        // only the width was reserved (`maxWidth: .infinity`), so the height
        // popped from ~nothing to width÷aspect on load. 3:4 matches the library
        // thumbnail proportion (LibraryViewComponents / InfoTab header).
        Color.clear
            .aspectRatio(3.0 / 4.0, contentMode: .fit)
            .frame(maxWidth: .infinity)
            .overlay {
                LibraryImageView(documentId: page.id, imageType: .display)
                    .aspectRatio(contentMode: .fit)
            }
            .background(RoundedRectangle(cornerRadius: 6).fill(.quaternary))
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .strokeBorder(isSelected ? Color.accentColor : Color.clear, lineWidth: 3)
            )
            .contentShape(Rectangle())
            // Single click selects; a second click opens — matches List(selection:)
            // behavior without fighting it (this grid isn't inside a List).
            .onTapGesture(count: 2, perform: onOpen)
            .onTapGesture(perform: onSelect)
            // #4416: a page's raw `name` is the upload temp filename — VoiceOver
            // would read `fichero_upload_c84fgjke.pdf` for every page in the grid.
            .accessibilityLabel(DocumentTitle.displayName(for: page))
            .accessibilityAddTraits(isSelected ? .isSelected : [])
    }
}
