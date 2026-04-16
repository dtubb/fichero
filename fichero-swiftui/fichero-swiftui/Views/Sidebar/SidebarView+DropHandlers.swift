import OSLog
import SwiftUI
import UniformTypeIdentifiers

/// Drop handlers scoped to the sidebar as a whole (not a specific row).
///
/// Per-row drops live in `SidebarItemRow+DropHandlers.swift`. This extension
/// handles top-level insertions — "drop a file between rows at library root" —
/// where the receiver is the library itself rather than a specific sidebar
/// item.
extension SidebarView {
    /// Handler for `.onInsert(of: [.fileURL])` on the top-level documents
    /// ForEach inside a library section. A drop between top-level rows means
    /// "import these files at library root" — `parentId = nil`.
    ///
    /// Offset is accepted but ignored until persistent sort-order lands
    /// (tracked in #572 — backend schema work).
    func handleLibraryRootInsert(
        libraryId: UUID,
        offset: Int,
        providers: [NSItemProvider]
    ) {
        guard let library = libraryManager.getLibrary(id: libraryId) else { return }

        Task {
            var fileURLs: [URL] = []
            for provider in providers where provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
                if let url = try? await Self.loadURLForRootInsert(from: provider) {
                    fileURLs.append(url)
                }
            }

            guard !fileURLs.isEmpty else { return }

            do {
                _ = try await library.importService.importFiles(
                    fileURLs,
                    mode: .link,
                    parentId: nil
                )
                await library.documentStore.refresh()
                try? await Task.sleep(for: .milliseconds(500))
                await library.documentStore.refresh()
            } catch {
                Logger(subsystem: "com.fichero.app", category: "SidebarRootDrop")
                    .error("Root insert failed: \(error.localizedDescription)")
            }
        }
    }

    private static func loadURLForRootInsert(from provider: NSItemProvider) async throws -> URL {
        try await withCheckedThrowingContinuation { continuation in
            _ = provider.loadObject(ofClass: URL.self) { url, error in
                if let error {
                    continuation.resume(throwing: error)
                } else if let url {
                    continuation.resume(returning: url)
                } else {
                    continuation.resume(throwing: NSError(domain: "SidebarRootInsert", code: -1))
                }
            }
        }
    }
}
