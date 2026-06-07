import SwiftUI

// MARK: - Preview

/// Self-contained visual preview of the sidebar's List + DisclosureGroup
/// + Label stack. No backend, no services, no bindings to real state —
/// just static SwiftUI so we can iterate on fonts, selection highlight,
/// and section-header weight via Xcode Previews (or
/// `mcp__xcode__RenderPreview`).
///
/// Keep this in sync with the styling choices in `LibrarySectionHeader`,
/// `SidebarView+ViewComponents.unifiedDisclosureSection`, and any other
/// rendering-only detail the real sidebar applies.
#Preview("Sidebar look") {
    SidebarVisualPreview()
        .frame(width: 260, height: 500)
}

private struct SidebarVisualPreview: View {
    @State private var selection: String? = "doc-a"
    @State private var librariesExpanded = true
    @State private var searchesExpanded = true

    var body: some View {
        List(selection: $selection) {
            Section {
                DisclosureGroup(isExpanded: $librariesExpanded) {
                    row(id: "doc-a", name: "Inbox", icon: "tray")
                    row(id: "doc-b", name: "Chota Valley", icon: "folder")
                    row(id: "doc-c", name: "Small Text", icon: "folder")
                    row(id: "doc-d", name: "Working", icon: "folder")
                } label: {
                    Text("Library")
                        .font(.caption)
                        .fontWeight(.bold)
                        .foregroundStyle(.primary)
                }
                DisclosureGroup(isExpanded: $searchesExpanded) {
                    row(id: "search-a", name: "New Search", icon: "magnifyingglass")
                    row(id: "search-b", name: "Colombia", icon: "magnifyingglass")
                    row(id: "search-c", name: "belcher", icon: "magnifyingglass")
                } label: {
                    Text("Saved Searches")
                        .font(.caption)
                        .fontWeight(.bold)
                        .foregroundStyle(.primary)
                }
            }
        }
        .listStyle(.sidebar)
        .scrollContentBackground(.hidden)
    }

    @ViewBuilder
    private func row(id: String, name: String, icon: String) -> some View {
        Label(name, systemImage: icon)
            .tag(id)
    }
}
