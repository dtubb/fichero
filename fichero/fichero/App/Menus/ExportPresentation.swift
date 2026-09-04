#if canImport(AppKit)
import AppKit
#endif
import Foundation
import UniformTypeIdentifiers

/// The panels and alerts every export shares.
///
/// Extracted from `FileMenuCommands+Export` (2026-09-03) so the reader's own
/// export commands present the SAME save panel, the same failure alert and the
/// same reveal-in-Finder as File ▸ Export — a second copy of these five lines
/// is how two exports start behaving differently.
enum ExportPresentation {
    #if os(macOS)
    /// A standard save panel seeded with `suggestedName`. A nil `contentType`
    /// leaves the panel's type filter alone — the caller's extension is then
    /// the only promise, which is what a type macOS does not declare needs.
    @MainActor
    static func savePanel(suggestedName: String, contentType: UTType?) async -> URL? {
        await withCheckedContinuation { continuation in
            let panel = NSSavePanel()
            panel.nameFieldStringValue = suggestedName
            if let contentType { panel.allowedContentTypes = [contentType] }
            panel.allowsOtherFileTypes = false
            panel.canCreateDirectories = true
            panel.begin { result in
                continuation.resume(returning: result == .OK ? panel.url : nil)
            }
        }
    }

    /// A folder chooser, for the exports that write more than one file.
    @MainActor
    static func directoryPanel(message: String) async -> URL? {
        await withCheckedContinuation { continuation in
            let panel = NSOpenPanel()
            panel.canChooseDirectories = true
            panel.canChooseFiles = false
            panel.canCreateDirectories = true
            panel.prompt = "Export Here"
            panel.message = message
            panel.begin { result in
                continuation.resume(returning: result == .OK ? panel.url : nil)
            }
        }
    }

    /// A failed export is never silent (#3305's sibling: nor is a successful one).
    @MainActor
    static func showError(_ error: Error, title: String) {
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = error.localizedDescription
        alert.alertStyle = .warning
        alert.runModal()
    }

    /// Reveal the exported file/folder in Finder so a successful export isn't
    /// silent (#3305).
    @MainActor
    static func revealInFinder(_ url: URL) {
        NSWorkspace.shared.activateFileViewerSelecting([url])
    }
    #endif
}
