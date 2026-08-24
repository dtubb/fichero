import SwiftUI

/// The preview pane's lens list. One honest entry today — the source media —
/// so the head reads the same grammar as every pane; annotation/edit lenses
/// join as they are unified here (Daniel, 2026-08-23).
enum PreviewLens: String, CaseIterable, Identifiable {
    case source

    var id: String { rawValue }
    var title: String { "Source" }
    var icon: String { "photo" }
}
