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
