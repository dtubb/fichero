import SwiftUI

/// Which bottom edge a window column keeps clear (owner, 2026-11-13, #6570). The iPhone keeps the home indicator's area clear,
/// so its bottom bars sit above it. On the iPad that left every column's bottom bar about 20 points above the screen's
/// edge, which read as a margin too high for a desktop-style window; there each column runs into it and its bar sits at
/// the bottom, as the Mac's do. Applied at each column's root (sidebar, content, Inspector): the split view keeps a
/// safe area per column, so a modifier outside the columns changed nothing.
enum BottomSafeAreaPolicy {
    static func ignoredEdges(isIOS: Bool, isCompact: Bool) -> Edge.Set {
        isIOS && !isCompact ? .bottom : []
    }
}

extension View {
    /// `BottomSafeAreaPolicy` for one window column.
    @ViewBuilder
    func columnBottomEdge(isCompact: Bool) -> some View {
        #if os(iOS)
        ignoresSafeArea(.container, edges: BottomSafeAreaPolicy.ignoredEdges(isIOS: true, isCompact: isCompact))
        #else
        self
        #endif
    }
}
