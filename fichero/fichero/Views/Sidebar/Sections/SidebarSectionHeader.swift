import OSLog
import SwiftUI
import UniformTypeIdentifiers

// Note: The previous `SidebarSectionHeader` (a Label-styled header with a
// String-only drop target) was removed after a code review confirmed it had
// zero call sites — sub-section labels in the sidebar use plain `Text`
// instead (see `SidebarView+ViewComponents.unifiedDisclosureSection`). Kept
// this file focused on `LibrarySectionHeader` below, which IS used as the
// library-name row and now accepts Finder URL drops (#582).

/// VoiceOver value for a library header row: the current-library state is
/// otherwise only conveyed by the accent icon tint (#584 follow-up).
func sidebarLibraryHeaderAccessibilityValue(isCurrent: Bool) -> String {
    isCurrent ? "current library" : ""
}

// MARK: - Library Section Header

/// Section header specifically for library grouping across sidebar modes.
/// Displays the library name (or "Global" for the global library) with an item count.
/// Shows a checkmark indicator when this library is the current active library.
///
/// Accepts Finder file URL drops at library root — previously had no drop
/// destination, which meant Finder drops on the library-name row silently
/// did nothing (#582). `onFileDrop` callers pass a closure that imports
/// the URLs into the library root via `importService.importFiles(...,
/// parentId: nil)`.
///
/// Uses the NSItemProvider drop API rather than the Transferable one so Finder
/// folder drags preserve the folder URL instead of being flattened into the
/// folder's child files (#587). It accepts `SidebarItemRow.dropTypes` — the
/// same list the rows accept — because internal sidebar drags arrive here too,
/// and routing them by capability rather than by the id they carry is what made
/// a move into a copy (#4401).
struct LibrarySectionHeader: View {
    let library: LibraryManager.LibraryReference
    let itemCount: Int
    var isCurrentLibrary: Bool = false
    var onFileDrop: (([URL]) -> Bool)?
    /// In-app drop receiver for sidebar items dragged onto the library
    /// header — reparents them to the library root (parentId = nil) so
    /// the user can lift items out of nested folders and then reorder
    /// them at root via native row drops. Added to satisfy #711's
    /// "let me drop on the library at the top" workflow.
    var onSidebarItemDrop: (([String]) -> Void)?
    /// Where a refused or unreadable drop is reported. The header accepted the
    /// drop synchronously, so having nowhere to say "that did nothing" is how a
    /// file appears to vanish.
    var onDropError: ((String) -> Void)?
    var onTap: (() -> Void)?

    @State private var isDropTargeted = false

    var body: some View {
        headerContent
            .padding(.vertical, 2)
            .contentShape(Rectangle())
            .background(
                RoundedRectangle(cornerRadius: SidebarConstants.cornerRadius)
                    .fill(
                        isDropTargeted
                            ? Color.accentColor.opacity(0.25)
                            : Color.clear
                    )
            )
            // ONE drop handler (#4401 follow-up). There used to be two on this
            // same view — an `.onDrop(of: [.fileURL])` that imported, and a
            // `.dropDestination(for: SidebarDragID.self)` that moved — and
            // since #4123 an internal DOCUMENT drag vends a real file, so it
            // satisfied the import handler's `canLoadObject(ofClass: URL.self)`
            // filter and was re-ingested as a brand-new hollow document. That
            // is the same regression #4401 fixed inside `handleRowDrop`; the
            // fix never reached this second, independent implementation.
            //
            // Folders were unaffected and that is the tell: `SidebarDragID`
            // only sets `documentId` for non-folders, so a folder row exports
            // no file, never matched the import handler, and moved correctly.
            //
            // Merging them removes the question of which modifier wins, which
            // is not something source review can answer and not something to
            // leave load-bearing.
            .onDrop(of: SidebarItemRow.dropTypes, isTargeted: $isDropTargeted) { providers in
                handleLibraryHeaderDrop(providers)
            }
            // Sidebar plan Step 10 (#584): VoiceOver label reads e.g.
            // "Global, library, 42 documents". Hint guides users toward the
            // Finder-drop behaviour that isn't obvious without visual cues.
            .accessibilityLabel(accessibilityLabel)
            // The accent-tinted icon is the only VISUAL "this is the current
            // library" signal — expose the same state non-visually.
            .accessibilityValue(sidebarLibraryHeaderAccessibilityValue(isCurrent: isCurrentLibrary))
            .accessibilityHint(
                "Drag files from Finder to import, or drop a sidebar item to move to the library root."
            )
            // Full name on hover — the name Text can truncate in a narrow
            // sidebar and has no other way to reveal itself.
            .help(libraryName)
    }

    /// Display name for this library row. "Global" for the global library,
    /// the user's display name otherwise.
    private var libraryName: String {
        library.id == LibraryManager.globalLibraryId ? "Global" : library.displayName
    }

    /// Row content — extracted into a `@ViewBuilder` to keep the body
    /// expression small enough for SourceKit to type-check in bounded
    /// time. The combined HStack with three conditional branches used
    /// to trip the "compiler unable to type-check this expression in
    /// reasonable time" warning (2026-04-17 review).
    @ViewBuilder
    private var headerContent: some View {
        HStack(spacing: 6) {
            Image(systemName: "books.vertical")
                .foregroundStyle(isCurrentLibrary ? Color.accentColor : Color.primary)
                .font(.system(size: 13))
            Text(libraryName)
            locationBadge
            LibrarySharingBadge(library: library)
            Spacer()
            if itemCount > 0 {
                Text("\(itemCount)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .simultaneousGesture(TapGesture().onEnded { onTap?() })
    }

    /// Small badge showing WHERE this library's engine lives — local embedded
    /// engine vs a named remote device/host (#2574). Reads
    /// `LibraryReference.locationDescriptor`; icon-only inline with a
    /// `.help`/accessibility label carrying the full "On <device>" text so the
    /// row stays compact.
    @ViewBuilder
    private var locationBadge: some View {
        let location = library.locationDescriptor
        Image(systemName: location.systemImage)
            .font(.caption)
            .foregroundStyle(.secondary)
            .help(location.label)
            .accessibilityLabel(location.label)
    }

    private var accessibilityLabel: String {
        let location = library.locationDescriptor.label
        if itemCount > 0 {
            let plural = itemCount == 1 ? "document" : "documents"
            return "\(libraryName), library, \(location), \(itemCount) \(plural)"
        }
        return "\(libraryName), library, \(location)"
    }

    /// Route a drop on the library header, identifying an internal drag
    /// POSITIVELY by the `doc:` id it carries rather than by the absence of
    /// anything file-shaped (#4401).
    ///
    /// Shares `classifySidebarDropPayload` with the row path deliberately: two
    /// copies of this decision is exactly what produced the bug, and the
    /// classifier is pure, so both paths are pinned by the same tests.
    private func handleLibraryHeaderDrop(_ providers: [NSItemProvider]) -> Bool {
        guard !providers.isEmpty else { return false }

        let capabilities = providers.map {
            SidebarDropProviderCapabilities(
                canLoadURL: $0.canLoadObject(ofClass: URL.self),
                canLoadString: $0.canLoadObject(ofClass: NSString.self),
                registeredTypeIdentifiers: $0.registeredTypeIdentifiers
            )
        }
        let hasFileURL = capabilities.contains(where: \.canLoadURL)
        let mightBeInternal = sidebarDropMightCarryInternalID(capabilities)
        guard mightBeInternal || hasFileURL else { return false }

        Task {
            var loadedIDs: [String] = []
            for provider in providers where provider.canLoadObject(ofClass: NSString.self) {
                if let string = try? await Self.loadString(from: provider) {
                    loadedIDs.append(string)
                }
            }
            switch classifySidebarDropPayload(
                loadedIDs: loadedIDs,
                hasFileURL: hasFileURL,
                carriesOwnProcessFlavor: mightBeInternal
            ) {
            case .internalItems(let ids):
                guard let onSidebarItemDrop else { return }
                await MainActor.run { onSidebarItemDrop(ids) }

            case .externalFiles:
                await importExternalDrop(providers)

            case .unreadableInternal:
                // Started inside the app and unreadable. Importing would create
                // the hollow duplicate this issue is about — refuse and say so.
                Logger(subsystem: "app.fichero.fichero", category: "LibraryHeaderDrop")
                    .error("Library-header drop came from inside the app with no readable id; refusing to import")
                await MainActor.run {
                    onDropError?("Couldn't read what was dragged. Nothing was moved or imported.")
                }

            case .unsupported:
                break
            }
        }
        return true
    }

    /// The genuine-Finder-drag branch: load every URL the providers will give
    /// and hand them to the importer.
    private func importExternalDrop(_ providers: [NSItemProvider]) async {
        guard let onFileDrop else { return }
        var urls: [URL] = []
        for provider in providers where provider.canLoadObject(ofClass: URL.self) {
            if let url = try? await Self.loadURL(from: provider) {
                urls.append(url)
            }
        }
        guard !urls.isEmpty else {
            // The OS was already told the drop was accepted, so a silent
            // return vanishes the file with no explanation (#4459's rule).
            await MainActor.run {
                onDropError?("Couldn't read the dropped item(s). Nothing was imported.")
            }
            return
        }
        _ = await MainActor.run { onFileDrop(urls) }
    }

    private static func loadString(from provider: NSItemProvider) async throws -> String {
        try await withCheckedThrowingContinuation { continuation in
            _ = provider.loadObject(ofClass: NSString.self) { value, error in
                if let error {
                    continuation.resume(throwing: error)
                } else if let nsString = value as? NSString {
                    continuation.resume(returning: nsString as String)
                } else {
                    continuation.resume(throwing: NSError(domain: "LibraryHeaderDrop", code: -1))
                }
            }
        }
    }

    private static func loadURL(from provider: NSItemProvider) async throws -> URL {
        try await withCheckedThrowingContinuation { continuation in
            _ = provider.loadObject(ofClass: URL.self) { url, error in
                if let error {
                    continuation.resume(throwing: error)
                } else if let url {
                    continuation.resume(returning: url)
                } else {
                    continuation.resume(throwing: NSError(domain: "LibraryHeaderDrop", code: -1))
                }
            }
        }
    }
}
