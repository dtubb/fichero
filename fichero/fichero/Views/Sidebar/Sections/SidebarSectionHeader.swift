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
    /// Import callback. The mode matters (#4459 family, live-repro
    /// 2026-08-04): URLs the loader staged into a `fichero-drop-*` temp
    /// directory must be COPY-ingested before the directory is torn down,
    /// while stable URLs (a real Finder file, an open-in-place folder) are
    /// linked exactly like a folder chosen via the import menu.
    var onFileDrop: (([URL], IngestMode) -> Bool)?
    /// In-app drop receiver for sidebar items dragged onto the library
    /// header — applies the Finder modifier grammar at the library root
    /// (plain = reparent, ⌥ = copy, ⌘⌥ = alias; modifiers sampled at the
    /// drop entry point) so the user can lift items out of nested folders
    /// and then reorder them at root via native row drops. Added to satisfy
    /// #711's "let me drop on the library at the top" workflow.
    var onSidebarItemDrop: (([String], SidebarDropModifiers) -> Void)?
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
            // The same platter the item rows use (#4568, Daniel: "also for
            // modes not just folders") — the ENTIRE row solid accent while
            // targeted, never the old label-bounded 0.25 wash that made the
            // library header's target look different from a folder's.
            .sidebarDropHighlight(isDropTargeted)
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
            //
            // The DELEGATE form for the same reason the rows use it (#4401
            // reopened): the closure form cannot propose an operation, so
            // SwiftUI proposed `.copy` and the cursor showed a `+` over a drop
            // this handler performs as a move to the library root.
            .onDrop(
                of: SidebarItemRow.dropTypes,
                delegate: LibraryItemDropDelegate(
                    acceptedTypes: SidebarItemRow.dropTypes,
                    isTargeted: $isDropTargeted,
                    surface: "sidebar-library-header",
                    onDropProviders: { handleLibraryHeaderDrop($0) }
                )
            )
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
                // White over the solid accent drop platter — the same
                // inversion rule as the item rows (rowContentColor, #4568).
                .foregroundStyle(
                    isDropTargeted ? Color.white
                        : isCurrentLibrary ? Color.accentColor : Color.primary
                )
                // #4098: `.body` rather than `.system(size: 13)`. This icon
                // sits beside `Text(libraryName)`, which carries no explicit
                // font and is therefore body — so the hardcoded 13pt was
                // hand-matching body at the DEFAULT text size only, and drifted
                // out of step the moment the user changed it.
                .font(.body)
            Text(libraryName)
                .foregroundStyle(isDropTargeted ? Color.white : Color.primary)
            locationBadge
            LibrarySharingBadge(library: library)
            Spacer()
            if itemCount > 0 {
                Text("\(itemCount)")
                    .font(.caption)
                    .foregroundStyle(isDropTargeted ? AnyShapeStyle(Color.white) : AnyShapeStyle(.secondary))
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
        guard !providers.isEmpty else {
            // #4533: was silent.
            DragDropLog.refused("sidebar-library-header", reason: "no providers in the drop")
            return false
        }

        // Sample modifier state ONCE, at the drop entry point (#4475 C) —
        // the payload read below is async, and by the time it resolves the
        // user has released the keys. The header honors the same Finder
        // grammar as every other in-app drop target: plain = move to root,
        // ⌥ = copy to root, ⌘⌥ = alias at root.
        let modifiersAtDrop = SidebarDropModifiers.current()
        let capabilities = sidebarDropCapabilities(of: providers)
        // Registration-based (#4401 live-repro): a Finder FOLDER answers
        // canLoadObject(URL.self) == false, so the old canLoadURL guard
        // silently dropped folder drags on the header.
        let hasExternalPayload = capabilities.contains(where: \.registersExternalPayload)
        let mightBeInternal = sidebarDropMightCarryInternalID(capabilities)
        guard mightBeInternal || hasExternalPayload else {
            // #4533: the header's copy of the commonest silent refusal. Name
            // the UTIs — this is the guard that #4401 already had to fix once
            // for Finder folders, and the next payload shape that fails here
            // should not need a live repro to find.
            DragDropLog.refused(
                "sidebar-library-header",
                reason: "payload is neither an internal id nor an external payload — "
                    + "UTIs [\(capabilities.flatMap(\.registeredTypeIdentifiers).joined(separator: ", "))]"
            )
            return false
        }

        // Reads through the SHARED reader, like the row path and the library
        // folder cell. This used to be a third hand-rolled copy of the same
        // provider plumbing.
        Task {
            // Surface name matches the drop DELEGATE's ("sidebar-library-header")
            // — this used to log as "sidebar-section-header", so one physical
            // drop produced two differently-named log trails and read as two
            // performs (live report 2026-08-04).
            switch await readSidebarDropPayload(providers, surface: "sidebar-library-header") {
            case .internalItems(let ids):
                guard let onSidebarItemDrop else {
                    // #4533: a surface wired without its handler accepts the
                    // drop and drops it on the floor. Silent until now.
                    DragDropLog.refused(
                        "sidebar-library-header",
                        reason: "no onSidebarItemDrop handler bound (\(ids.count) internal item(s) lost)"
                    )
                    return
                }
                await MainActor.run { onSidebarItemDrop(ids, modifiersAtDrop) }

            case .externalFiles:
                await importExternalDrop(providers)

            case .unreadableInternal:
                // Started inside the app and unreadable. Importing would create
                // the hollow duplicate this issue is about — refuse and say so.
                // #4533: the LAST private "LibraryHeaderDrop" category, folded
                // into the shared seam so one filter shows a whole drop.
                DragDropLog.refused(
                    "sidebar-library-header",
                    reason: "came from inside the app with no readable id — refusing to import "
                        + "(importing would create the hollow duplicate this guard exists for)"
                )
                // NO alert (Daniel #136) — logged above; the drag snaps
                // back and nothing is lost.

            case .unsupported:
                // #4533: `break` — the drop reached the header, was classified,
                // and nothing happened, with no line anywhere. This is the
                // literal shape of "the drop did nothing and the log is empty".
                DragDropLog.refused(
                    "sidebar-library-header",
                    reason: "payload classified UNSUPPORTED — "
                        + "UTIs [\(providers.flatMap(\.registeredTypeIdentifiers).joined(separator: ", "))]"
                )
            }
        }
        return true
    }

    /// The genuine-Finder-drag branch: load every URL through the SHARED
    /// loader ladder and hand them to the importer.
    ///
    /// This used to iterate `providers where canLoadObject(ofClass: URL.self)`
    /// with its own weak `loadObject` — the exact instrument the classifier
    /// header warns about: a Finder FOLDER answers false to that probe
    /// (live-repro 2026-08-04), so a folder drop passed classification and
    /// then died here with "Couldn't read the dropped item(s)". One loader,
    /// every surface (#4184's rule); the row and library-cell paths already
    /// complied, this was the straggler.
    private func importExternalDrop(_ providers: [NSItemProvider]) async {
        guard let onFileDrop else {
            // #4533: same shape as the internal handler above.
            DragDropLog.refused(
                "sidebar-library-header",
                reason: "no onFileDrop handler bound (\(providers.count) external provider(s) lost)"
            )
            return
        }
        var stableURLs: [URL] = []
        var temporaryURLs: [URL] = []
        for provider in providers {
            if let url = try? await ExternalFileDropLoader.loadAnyFileURL(from: provider) {
                if url.path.contains("/fichero-drop-") {
                    temporaryURLs.append(url)
                } else {
                    stableURLs.append(url)
                }
            }
        }
        guard !stableURLs.isEmpty || !temporaryURLs.isEmpty else {
            // The OS was already told the drop was accepted, so a silent
            // return vanishes the file with no explanation (#4459's rule).
            // #4533: it told the USER but left no retrievable trace — name
            // which rung of the loader ladder came up empty.
            DragDropLog.refused(
                "sidebar-library-header",
                reason: "ExternalFileDropLoader resolved no URL from any of "
                    + "\(providers.count) provider(s); nothing imported"
            )
            await MainActor.run {
                onDropError?("Couldn't read the dropped item(s). Nothing was imported.")
            }
            return
        }
        await MainActor.run {
            if !stableURLs.isEmpty { _ = onFileDrop(stableURLs, .link) }
            if !temporaryURLs.isEmpty { _ = onFileDrop(temporaryURLs, .copy) }
        }
    }
}
