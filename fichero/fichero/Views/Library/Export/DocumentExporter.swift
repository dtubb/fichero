import SwiftUI
#if os(macOS)
import AppKit
#endif

/// Context-menu "Export…" (#4121): fetch the document's source file through
/// its library's storage service — the SAME path the Finder drag-out uses
/// (#4123), so naming/auth/remote-engine behavior can't diverge — then save
/// it where the user picks. Save-panel UI is macOS-only; iOS relies on the
/// system share sheet elsewhere.
enum DocumentExporter {
    @MainActor
    static func exportViaSavePanel(
        _ dragID: SidebarDragID,
        onError: @escaping (String) -> Void
    ) {
        #if os(macOS)
        Task { @MainActor in
            do {
                let source = try await SidebarDragID.exportSourceFile(for: dragID)
                let panel = NSSavePanel()
                panel.nameFieldStringValue = source.lastPathComponent
                panel.canCreateDirectories = true
                guard panel.runModal() == .OK, let destination = panel.url else { return }
                // The panel already confirmed replacement with the user.
                if FileManager.default.fileExists(atPath: destination.path) {
                    try FileManager.default.removeItem(at: destination)
                }
                try FileManager.default.moveItem(at: source, to: destination)
            } catch {
                onError("Export failed: \(error.localizedDescription)")
            }
        }
        #endif
    }
}
