import SwiftUI

/// The Documents / Claims / Entities picker — the node-model axis (which KIND of
/// node the library browses). It lives in the library PANE HEAD beside the
/// view-mode picker: WHAT you're browsing sits next to HOW it's laid out.
///
/// A concrete named type (not an inline `some View`) so the `PaneHead`'s
/// generic `Controls` parameter stays nameable and its body keeps its explicit,
/// type-check-budgeted shape.
struct LibraryContentKindControl: View {
    /// Bound to `LibraryView.contentKindBinding` (#4884: displays the pane's
    /// EFFECTIVE kind, writes an explicit per-pane choice); the setter clears
    /// the selection so a document-id selection can't leak into the claims /
    /// entities list, where the ids mean something else.
    @Binding var kind: LibraryContentKind

    /// #4966: `ViewThatFits` — the SAME primitive `PaneKindSelector`'s own
    /// header ladder and the bottom bar's `AdaptiveMiniToolbarRow` are both
    /// built on, not a second collapse mechanism. Before this, `.fixedSize()`
    /// held the label at its ideal ("Documents" + icon) width and let the
    /// PARENT clip it mid-word ("Documen") instead of the control itself
    /// choosing to drop to its icon — the exact defect #4966 named.
    var body: some View {
        ViewThatFits(in: .horizontal) {
            control(iconOnly: false)
            control(iconOnly: true)
        }
    }

    private func control(iconOnly: Bool) -> some View {
        Menu {
            Picker("Browse", selection: $kind) {
                ForEach(LibraryContentKind.allCases) { candidate in
                    Label(candidate.label, systemImage: candidate.systemImage).tag(candidate)
                }
            }
            .pickerStyle(.inline)
            .labelsHidden()
        } label: {
            // Two label styles are two TYPES, so a ternary cannot choose between them.
            if iconOnly {
                Label(kind.label, systemImage: kind.systemImage).labelStyle(.iconOnly)
            } else {
                Label(kind.label, systemImage: kind.systemImage).labelStyle(.titleAndIcon)
            }
        }
        .fixedSize()
        .help("Browse documents, claims, or entities in this folder")
        .accessibilityLabel("Browse kind: \(kind.label)")
    }
}
