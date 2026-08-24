import SwiftUI

/// The preview pane's lenses (Daniel, 2026-08-23: "preview and edit — that
/// feels correct"). The lens never changes WHICH document shows, only how.
enum PreviewLens: String, CaseIterable, Identifiable {
    case preview
    case edit

    var id: String { rawValue }

    var title: String {
        switch self {
        case .preview: "Preview"
        case .edit: "Edit"
        }
    }

    var icon: String {
        switch self {
        case .preview: "photo"
        case .edit: "pencil"
        }
    }
}
