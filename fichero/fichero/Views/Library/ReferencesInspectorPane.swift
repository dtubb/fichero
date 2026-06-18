import FicheroAPIClient
import SwiftUI

/// The References inspector tab, built as List + detail (#2005, EPIC #2002).
///
/// Mirrors `ArtifactsInspectorPane`: a vertical split with a lightweight
/// `ReferenceListView` on top and a single `ReferenceDetailView` below that
/// follows the selection. A toolbar button tears the detail off into a separate
/// `ReferenceDetailWindow` that also follows selection.
///
/// Replaces the stacked `DocumentBibliographyPanel` that lived as a section
/// inside the Info tab. Data comes from the document-scoped `ReferenceStore`
/// (#1999). Read-only: references are extracted data, so there's no
/// save/delete path.
struct ReferencesInspectorPane: View {
    let document: Document

    @Environment(ReferenceStore.self) private var store
    @Environment(\.openWindow) private var openWindow

    /// Shared selection — the same instance the detached window observes.
    @State private var focused = FocusedReference.shared

    /// Flattened items, resolved live from the store.
    private var items: [ReferenceItem] {
        let selfItems = store.selfRef.map { [ReferenceItem(reference: $0, isSelf: true)] } ?? []
        return selfItems + store.references.map { ReferenceItem(reference: $0, isSelf: false) }
    }

    private var selectedItem: ReferenceItem? {
        focused.id.flatMap { id in items.first { $0.id == id } }
    }

    var body: some View {
        VStack(spacing: 0) {
            if let loadError = store.loadError {
                errorBox(loadError)
            }
            PlatformVSplitView {
                ReferenceListView(
                    store: store,
                    focused: focused,
                    onOpenInWindow: openDetailWindow
                )
                .frame(minHeight: 120, idealHeight: 200)

                ReferenceDetailView(item: selectedItem)
                    .frame(minHeight: 160)
            }
        }
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Button {
                    openDetailWindow()
                } label: {
                    Label("Open in Window", systemImage: "macwindow.badge.plus")
                }
                .help("Open the selected reference in a separate window")
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
        focused.resolve(in: items)
        openWindow(id: "reference-detail")
    }

    @ViewBuilder
    private func errorBox(_ message: String) -> some View {
        HStack(alignment: .top, spacing: 6) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Button("Retry") {
                Task { await store.setScope(documentId: document.id, force: true) }
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.orange.opacity(0.1))
    }
}

/// The torn-off reference-detail window (#2005). A separate, naturally-draggable
/// scene that renders the selected reference read-only and, by default,
/// **follows the inspector's selection** via the shared `FocusedReference`. A
/// pin toggle parks the window on the current reference.
struct ReferenceDetailWindow: View {
    @State private var focused = FocusedReference.shared

    @State private var isPinned = false
    @State private var pinnedItem: ReferenceItem?

    private var shownItem: ReferenceItem? {
        isPinned ? pinnedItem : focused.item
    }

    var body: some View {
        ReferenceDetailView(item: shownItem)
            .navigationTitle(shownItem?.title ?? "Reference")
            .navigationSubtitle(focused.documentName ?? "")
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
                            ? "Pinned to this reference — won't follow selection"
                            : "Following the inspector's selection"
                    )
                    .onChange(of: isPinned) { _, pinned in
                        pinnedItem = pinned ? focused.item : nil
                    }
                }
            }
            .frame(minWidth: 360, minHeight: 320)
    }
}
