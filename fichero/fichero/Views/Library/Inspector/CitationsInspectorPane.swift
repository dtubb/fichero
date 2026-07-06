import FicheroAPIClient
import SwiftUI

/// The Citations inspector tab, built as List + detail (#2004, EPIC #2002).
///
/// Mirrors `ArtifactsInspectorPane`: a horizontal split with a lightweight
/// `CitationListView` on the left and a single `CitationDetailView` on the
/// right that follows the selection. A toolbar button tears the detail off
/// into a separate `CitationDetailWindow` that also follows selection.
///
/// Replaces the stacked `CitationGraphPanel` that lived as a section inside the
/// Info tab. Data comes from the document-scoped `CitationStore` (#1998) — the
/// sanctioned reactive source. Read-only: citations are extracted data, so
/// there's no save/delete path.
struct CitationsInspectorPane: View {
    let document: Document

    @Environment(CitationStore.self) private var store
    @Environment(\.openWindow) private var openWindow
    @Environment(\.supportsMultipleWindows) private var supportsMultipleWindows

    /// Shared selection — the same instance the detached window observes.
    @State private var focused = FocusedCitation.shared

    /// Flattened items, resolved live from the store so change-stream echoes
    /// flow through immediately.
    private var items: [CitationItem] {
        store.outbound.map { CitationItem(citation: $0, direction: .outbound) }
            + store.inbound.map { CitationItem(citation: $0, direction: .inbound) }
    }

    private var selectedItem: CitationItem? {
        focused.id.flatMap { id in items.first { $0.id == id } }
    }

    var body: some View {
        PlatformHSplitView {
            CitationListView(
                store: store,
                focused: focused,
                onOpenInWindow: openDetailWindow
            )
            .frame(minHeight: 120, idealHeight: 200)

            CitationDetailView(item: selectedItem, usages: store.usages)
                .frame(minHeight: 160)
        }
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Button {
                    openDetailWindow()
                } label: {
                    Label("Open in Window", systemImage: "macwindow.badge.plus")
                }
                .help("Open the selected citation in a separate window")
                .disabled(focused.id == nil)
            }
        }
        .task(id: document.id) {
            focused.clear()
            focused.documentName = document.name
            await store.setScope(documentId: document.id, force: true)
        }
    }

    private func openDetailWindow() {
        // No-op on single-window platforms (iPhone) so the button isn't a silent
        // dead affordance (#2805).
        guard supportsMultipleWindows else { return }
        focused.resolve(in: items)
        openWindow(id: "citation-detail")
    }
}

/// The torn-off citation-detail window (#2004). A separate, naturally-draggable
/// scene that renders the selected citation read-only and, by default,
/// **follows the inspector's selection** via the shared `FocusedCitation`. A pin
/// toggle parks the window on the current citation.
struct CitationDetailWindow: View {
    @State private var focused = FocusedCitation.shared

    @State private var isPinned = false
    @State private var pinnedItem: CitationItem?

    private var shownItem: CitationItem? {
        isPinned ? pinnedItem : focused.item
    }

    var body: some View {
        CitationDetailView(item: shownItem)
            .navigationTitle(shownItem.map { citationTitle($0) } ?? "Citation")
            #if !os(visionOS)
            .navigationSubtitle(focused.documentName ?? "")
            #endif
            .toolbar {
                ToolbarItem(placement: .automatic) {
                    Toggle(isOn: $isPinned) {
                        Label(
                            isPinned ? "Pinned" : "Following selection",
                            systemImage: isPinned ? "pin.fill" : "pin"
                        )
                    }
                    .toggleStyle(.button)
                    .help(
                        isPinned
                            ? "Pinned to this citation — won't follow selection"
                            : "Following the inspector's selection"
                    )
                    .onChange(of: isPinned) { _, pinned in
                        pinnedItem = pinned ? focused.item : nil
                    }
                }
            }
            .frame(minWidth: 360, minHeight: 320)
    }

    private func citationTitle(_ item: CitationItem) -> String {
        let text = item.citation.targetCitationText
        return text.count > 60 ? String(text.prefix(60)) + "…" : text
    }
}
