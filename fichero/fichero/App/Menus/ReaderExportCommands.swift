import SwiftUI
import UniformTypeIdentifiers

// MARK: - Export what you are READING (Daniel, 2026-09-03)

/// The documents the focused Reader is showing, and the text it is showing for
/// them — the payload behind File ▸ Export ▸ Markdown/Word and the reader
/// head's own context menu.
///
/// Published by `ReadingPaneView` and by nothing else, so the commands disable
/// themselves outside a reader instead of teasing a verb that cannot apply —
/// the same contract `readerLens` and `readerZoomActions` keep.
///
/// The `items` honour the visible-surface selection ruling: a multi-selection
/// exports every document the pane is rendering, a single selection exports
/// the one. `Equatable` on the IDS only — the text rides along for the
/// Markdown path, and byte-comparing whole transcripts on every body pass is
/// exactly the republish storm `SidebarActions` documents.
struct ReaderExportTargets: Equatable {
    struct Item: Equatable {
        let id: String
        /// Display name, already resolved through `DocumentTitle`.
        let name: String
        /// The reading text — the same string the proxy icon drags.
        let text: String
    }

    let items: [Item]

    /// Only the items with something to write. An unread page promises no
    /// Markdown, exactly as the proxy-icon drag refuses to.
    var markdownItems: [Item] { items.filter { !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty } }

    var isEmpty: Bool { items.isEmpty }

    /// File-name stem for a single-document save panel; the count for a
    /// multi-selection, which lands in a folder instead.
    var suggestedStem: String {
        items.count == 1 ? items[0].name : "\(items.count) Documents"
    }

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.items.map(\.id) == rhs.items.map(\.id)
            && lhs.markdownItems.count == rhs.markdownItems.count
    }
}

struct ReaderExportTargetsKey: FocusedValueKey {
    typealias Value = ReaderExportTargets
}

extension FocusedValues {
    var readerExportTargets: ReaderExportTargetsKey.Value? {
        get { self[ReaderExportTargetsKey.self] }
        set { self[ReaderExportTargetsKey.self] = newValue }
    }
}

// MARK: - The two menu items

/// "Export as Markdown..." and "Export as Word...", for the File ▸ Export submenu
/// and the reader head's context menu.
///
/// Two items and a save panel, deliberately: the FORMAT is the choice, so
/// there is no options sheet to fill in (dead-simple UX). Resolves the library
/// itself so it can be dropped into any menu without threading state through.
struct ReaderExportMenuItems: View {
    @Environment(LibraryManager.self) private var libraryManager
    @FocusedValue(\.readerExportTargets) private var targets

    private var currentLibrary: LibraryManager.LibraryReference? {
        guard let libraryId = libraryManager.currentLibraryId else { return nil }
        return libraryManager.getLibrary(id: libraryId)
    }

    var body: some View {
        // macOS ONLY, and this gate is the point (#116/#4505): both handlers
        // need a save panel that does not exist on iOS, so on iPad these would
        // render as ENABLED commands with empty bodies. Absent beats a command
        // that cannot work.
        #if os(macOS)
        Group {
            // No library round-trip: the Markdown IS the text the reader is
            // showing, so this writes without asking an engine that may be on
            // another machine.
            Button {
                guard let targets else { return }
                Task { await ReaderExportRunner.exportMarkdown(targets: targets) }
            } label: {
                Label("Export as Markdown...", systemImage: "doc.plaintext")
            }
            .disabled(targets?.markdownItems.isEmpty != false)

            Button {
                guard let targets, let library = currentLibrary else { return }
                Task { await ReaderExportRunner.exportWord(targets: targets, library: library) }
            } label: {
                Label("Export as Word...", systemImage: "doc.richtext")
            }
            .disabled(currentLibrary == nil || targets?.isEmpty != false)
        }
        #else
        EmptyView()
        #endif
    }
}
