import SwiftUI

extension ImmersiveReaderView {
    /// Add a page-scoped reading mark (star / bookmark) for the current page
    /// without leaving full screen (#3548). Page-anchored, so it persists as a
    /// reading mark in the Notes layer regardless of re-layout.
    func markCurrentPage(kind: AnnotationKind, label: String) {
        guard let store = annotationStore else { return }
        Task {
            _ = await store.addNote(scope: .page(document.id), text: "", kind: kind)
            markConfirmation = label
            revealControls()
            try? await Task.sleep(for: .seconds(1.5))
            if markConfirmation == label { markConfirmation = nil }
        }
    }

    func revealControls() {
        if !controlsVisible {
            withAnimation(.easeInOut(duration: 0.15)) { controlsVisible = true }
        }
        hideTask?.cancel()
        hideTask = Task { @MainActor in
            try? await Task.sleep(for: .seconds(2.5))
            guard !Task.isCancelled else { return }
            withAnimation(.easeInOut(duration: 0.4)) { controlsVisible = false }
        }
    }

    func exit() {
        hideTask?.cancel()
        isPresented = false
    }
}
