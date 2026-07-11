import FicheroAPIClient
import SwiftUI

/// Annotations inspector built as List + detail.
///
/// The parent supplies the current list slice (usually filtered) while the pane
/// owns the shared focus, the window tear-off, and the action-layer mutations.
struct AnnotationsInspectorPane: View {
    let document: Document
    let annotations: [DocumentAnnotation]

    @Environment(AnnotationStore.self) private var annotationStore
    @Environment(\.openWindow) private var openWindow
    @Environment(\.supportsMultipleWindows) private var supportsMultipleWindows

    @Bindable var focused: FocusedAnnotation

    private var selectedAnnotation: DocumentAnnotation? {
        focused.id.flatMap { id in annotations.first { $0.id == id } }
    }

    var body: some View {
        VStack(spacing: 0) {
            if let loadError = annotationStore.loadError {
                errorBox(loadError)
            }
            InspectorListDetailSplit {
                AnnotationListView(
                    annotations: annotations,
                    focused: focused,
                    onOpenInWindow: openDetailWindow
                )
            } detail: {
                AnnotationDetailView(
                    annotation: selectedAnnotation,
                    onSave: { annotation, text in
                        try await saveAnnotation(annotation, text: text)
                    },
                    onDelete: { annotation in
                        try await deleteAnnotation(annotation)
                    },
                    onPromote: { annotation in
                        try await promoteAnnotation(annotation)
                    },
                    onCopyCrop: { annotation in
                        await copyCrop(annotation)
                    },
                    onReveal: { annotation in
                        reveal(annotation)
                    }
                )
            }
            Divider()
            InspectorBottomMiniToolbar(statusText: annotationsToolbarStatusText) {
                Button {
                    Task {
                        await annotationStore.loadAnnotations(for: annotationScope, force: true)
                    }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .buttonStyle(.plain)
                .help("Reload annotations")
                .accessibilityLabel("Reload annotations")

                Button {
                    openDetailWindow()
                } label: {
                    Image(systemName: "macwindow.badge.plus")
                }
                .buttonStyle(.plain)
                .help("Open the selected annotation in a separate window")
                .accessibilityLabel("Open selected annotation in window")
                .disabled(focused.id == nil)
            }
        }
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Button {
                    openDetailWindow()
                } label: {
                    Label("Open in Window", systemImage: "macwindow.badge.plus")
                }
                .help("Open the selected annotation in a separate window")
                .disabled(focused.id == nil)
            }
        }
        .task(id: document.id) {
            focused.clear()
            focused.documentName = document.name
        }
        .onChange(of: annotations) { _, items in
            focused.resolve(in: items)
        }
    }

    private var annotationsToolbarStatusText: String {
        if let selectedAnnotation {
            if let pageLabel = selectedAnnotation.pageLabel, !pageLabel.isEmpty {
                return "\(selectedAnnotation.kind.label) · p. \(pageLabel)"
            }
            return selectedAnnotation.kind.label
        }
        return "\(annotations.count) annotations"
    }

    private func openDetailWindow() {
        // No-op on single-window platforms (iPhone) so the button isn't a silent
        // dead affordance (#2805).
        guard supportsMultipleWindows else { return }
        focused.resolve(in: annotations)
        openWindow(id: "annotation-detail")
    }

    private var annotationScope: AnnotationScope {
        switch document.docType {
        case .folder:
            return .folder(document.id)
        case .page:
            return .page(document.id)
        default:
            return .document(document.id)
        }
    }

    // Mutations route through the injected AnnotationStore — the sanctioned
    // observable data layer — instead of resolving an action service through
    // LibraryManager + WindowState (#3428). The store updates its published
    // `annotations` in place, so the list/detail refresh without a full reload.
    private func saveAnnotation(_ annotation: DocumentAnnotation, text: String) async throws {
        guard await annotationStore.updateText(id: annotation.id, text: text) != nil else {
            throw AnnotationInspectorActionError.failed
        }
        focused.resolve(in: annotationStore.annotations)
    }

    private func deleteAnnotation(_ annotation: DocumentAnnotation) async throws {
        guard await annotationStore.delete(id: annotation.id) else {
            throw AnnotationInspectorActionError.failed
        }
        if focused.id == annotation.id {
            focused.clear()
        }
    }

    private func promoteAnnotation(_ annotation: DocumentAnnotation) async throws {
        guard await annotationStore.promoteToClaim(id: annotation.id) else {
            throw AnnotationInspectorActionError.failed
        }
        focused.resolve(in: annotationStore.annotations)
    }

    private func copyCrop(_ annotation: DocumentAnnotation) async {
        guard let data = await annotationStore.cropAnnotation(id: annotation.id),
              let text = String(data: data, encoding: .utf8),
              !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return
        }
        PlatformPasteboard.writeString(text)
    }

    private func reveal(_ annotation: DocumentAnnotation) {
        guard let documentId = annotation.documentId else { return }
        var info: [String: Any] = ["documentId": documentId]
        if let pageLabel = annotation.pageLabel { info["pageLabel"] = pageLabel }
        if let bbox = annotation.bbox { info["bbox"] = bbox }
        if let charStart = annotation.charStart { info["charStart"] = charStart }
        if let charEnd = annotation.charEnd { info["charEnd"] = charEnd }
        NotificationCenter.default.post(
            name: .annotationSelectedInInspector,
            object: nil,
            userInfo: info
        )
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
                Task {
                    await annotationStore.loadAnnotations(for: annotationScope, force: true)
                }
            }
                .buttonStyle(.bordered)
                .controlSize(.small)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.orange.opacity(0.1))
    }
}

/// Raised when a store-routed annotation mutation reports failure, so the
/// detail view's existing error handling still fires (#3428).
enum AnnotationInspectorActionError: Error {
    case failed
}

/// The torn-off annotation-detail window.
struct AnnotationDetailWindow: View {
    @State private var focused = FocusedAnnotation.shared

    @State private var isPinned = false
    @State private var pinnedAnnotation: DocumentAnnotation?

    private var shownAnnotation: DocumentAnnotation? {
        isPinned ? pinnedAnnotation : focused.annotation
    }

    var body: some View {
        AnnotationDetailView(annotation: shownAnnotation)
            .navigationTitle(shownAnnotation.map { $0.kind.label } ?? "Annotation")
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
                            ? "Pinned to this annotation — won't follow selection"
                            : "Following the inspector's selection"
                    )
                    .onChange(of: isPinned) { _, pinned in
                        pinnedAnnotation = pinned ? focused.annotation : nil
                    }
                }
            }
            .frame(minWidth: 360, minHeight: 320)
    }
}
