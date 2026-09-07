import SwiftUI

/// The Documents / Claims / Entities picker — the node-model axis (which KIND of
/// node the library browses). It lives in the library PANE HEAD beside the
/// view-mode picker: WHAT you're browsing sits next to HOW it's laid out.
///
/// A concrete named type (not an inline `some View`) so the `PaneHead`'s
/// generic `Controls` parameter stays nameable and its body keeps its explicit,
/// type-check-budgeted shape.
struct LibraryContentKindControl: View {
    /// Bound to the library's `libraryContentKind`; the setter clears the
    /// selection so a document-id selection can't leak into the claims / entities
    /// list, where the ids mean something else.
    @Binding var kind: LibraryContentKind

    var body: some View {
        Menu {
            Picker("Browse", selection: $kind) {
                ForEach(LibraryContentKind.allCases) { candidate in
                    Label(candidate.label, systemImage: candidate.systemImage).tag(candidate)
                }
            }
            .pickerStyle(.inline)
            .labelsHidden()
        } label: {
            Label(kind.label, systemImage: kind.systemImage)
        }
        .fixedSize()
        .help("Browse documents, claims, or entities in this folder")
        .accessibilityLabel("Browse kind")
    }
}
