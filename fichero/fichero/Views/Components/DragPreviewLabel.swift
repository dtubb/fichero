import SwiftUI

/// The ONE drag preview for rows and tiles — environment-free BY CONTRACT.
///
/// Why (Daniel's crash stack, 2026-08-08 night): `.draggable`'s DEFAULT
/// preview re-hosts the source view in SwiftUI's own `NSHostingView`
/// (`PasteboardUtility.File` machinery, frame #51 of the crash), which
/// inherits NO environment — so a row/tile that reads a required
/// `@Environment(X.self)` kills the app the moment a drag begins. Every
/// `.draggable` in the sidebar and library passes THIS view as its explicit
/// preview instead: icon + name, Finder's drag look, and nothing that could
/// need an environment object. Never add an `@Environment` read here.
struct DragPreviewLabel: View {
    let name: String
    let systemImage: String

    var body: some View {
        Label(name, systemImage: systemImage.isEmpty ? "doc" : systemImage)
            .font(.body)
            .lineLimit(1)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 6))
    }
}

/// Finder-parity ROW drag preview (Daniel #134/#135, 2026-08-09: "it should
/// be the actual entire row", not a lozenge with a filename): icon + name on
/// a full row platter at list-row width. Deliberately environment-free — a
/// drag preview renders OUTSIDE the tab tree (the boundary crash class), so
/// it composes from the values it is handed, never from @Environment.
struct RowDragPreview: View {
    let name: String
    let systemImage: String

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: systemImage.isEmpty ? "doc" : systemImage)
                .foregroundStyle(Color.accentColor)
                .frame(width: 16)
            Text(name)
                .font(.body)
                .lineLimit(1)
                .truncationMode(.middle)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .frame(width: 320, alignment: .leading)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 6))
    }
}

/// Finder-parity TILE drag preview: the ACTUAL icon tile (well + thumbnail +
/// name), as dragged from icon view. `DocumentThumbnailView`'s only service
/// read (LibraryImageView → StorageService) is optional, so a preview host
/// with no environment degrades to the placeholder glyph instead of trapping.
struct TileDragPreview: View {
    let document: Document

    var body: some View {
        DocumentThumbnailView(document: document, isSelected: false)
            .padding(6)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10))
    }
}

extension View {
    /// Cap the concrete view type at a ForEach ROW boundary (2026-08-08 night
    /// crash #2): SwiftUI's value-witness copy of a row's fully-composed type
    /// (nested ExclusiveGestures from tap/drag modifiers) overflowed the
    /// stack inside `ForEachState.item` — the column-root erasure
    /// (`sidebarStyle()`) does not cover per-item copies. Apply BEFORE `.tag`
    /// so the selection trait stays outside the erasure. Load-bearing, like
    /// #4331 — do not remove.
    func sidebarRowTypeErased() -> AnyView { AnyView(self) }
}
