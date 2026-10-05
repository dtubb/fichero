import AppIntents
import Foundation
import SwiftUI

/// The UI verbs (#5453, `openapi.ui.verbs-are-the-click`): open a project, open a node, select nodes,
/// reveal a line, show a pane or an Inspector tab, take a screenshot. The App Intents (every device)
/// and the AppleScript commands (Mac) call these and nothing else, and each calls the method its click
/// calls -- never a second path. A verb that needs a window acts on `WindowState.front`.
@MainActor
enum UIVerbs {
    enum Failure: LocalizedError, Equatable {
        case noWindow
        case unknownPane(String)
        case unknownInspectorTab(String)
        case noLibrary

        var errorDescription: String? {
            switch self {
            case .noWindow: "No Fichero window is open."
            case .unknownPane(let name):
                "Not a pane: \(name). Panes: \(UIPane.allCases.map(\.rawValue).joined(separator: ", "))."
            case .unknownInspectorTab(let name):
                "Not an Inspector tab: \(name). Tabs: \(InspectorTab.allCases.map(\.rawValue).joined(separator: ", "))."
            case .noLibrary: "The window's project is not open."
            }
        }
    }

    /// File ▸ Open's click (`LibraryWindow.handleFileImport`): the project opened, and the front window
    /// shows it. Answers the project's id.
    @discardableResult
    static func openProject(at url: URL, manager: LibraryManager = .shared, in window: WindowState? = WindowState.front) -> UUID {
        let library = manager.openLibrary(at: url)
        window?.libraryId = library.id
        return library.id
    }

    /// A node opened as a click on its crumb or row opens it (`PaneCrumb`, the Segments pane): the
    /// sidebar's reveal selects it and shows it.
    static func openNode(_ id: String) {
        NotificationCenter.default.post(name: .sidebarRevealDocument, object: nil, userInfo: ["documentId": id])
    }

    /// The Library's selection set to these nodes, as clicking (and ⌘-clicking) them sets it.
    static func selectNodes(_ ids: [String], in window: WindowState? = WindowState.front) throws {
        guard let window else { throw Failure.noWindow }
        window.request(.select(ids))
    }

    /// Reveal segments in the linked Preview -- the Order list's double-click and the Reader's line
    /// click (`WindowState.revealSegments`). Answers the ids revealed; none when no Preview shows the page.
    static func revealSegments(
        _ ids: [String], documentId: String, in window: WindowState? = WindowState.front, store: SegmentStore? = nil
    ) throws -> [String] {
        guard let window else { throw Failure.noWindow }
        guard let store = store ?? window.library.map({ SegmentStore.shared(for: $0.segmentService) }) else {
            throw Failure.noLibrary
        }
        return window.revealSegments(ids, documentId: documentId, store: store)
    }

    /// A pane shown, as its View-menu item, toolbar button or pane menu shows it.
    static func showPane(_ pane: UIPane, in window: WindowState? = WindowState.front) throws {
        guard let window else { throw Failure.noWindow }
        window.request(.showPane(pane))
    }

    /// The Inspector shown at a tab, as clicking the tab shows it.
    static func showInspectorTab(_ tab: InspectorTab, in window: WindowState? = WindowState.front) throws {
        guard let window else { throw Failure.noWindow }
        window.request(.showInspectorTab(tab))
    }

    /// A picture of the front window, or of one pane in it, saved as a PNG at `path`. The app draws its
    /// own window (no screen recording). Answers the absolute path written.
    static func screenshot(of pane: UIPane? = nil, to path: String, in window: WindowState? = WindowState.front) throws -> String {
        try FicheroUICapture.capture(pane: pane, of: window, to: path)
    }
}

/// What a UI verb asks a window for. A token, so asking for the same thing twice acts twice.
struct UIVerbRequest: Equatable {
    enum Action: Equatable {
        case select([String])
        case showPane(UIPane)
        case showInspectorTab(InspectorTab)
    }

    let action: Action
    let token: Int
}

/// A pane by the name a verb uses (`openapi.ui.screenshot` names these five, plus the two other pane kinds).
enum UIPane: String, CaseIterable, AppEnum {
    case library, preview, reader, inspector, activity, chat, segments

    static let typeDisplayRepresentation = TypeDisplayRepresentation(name: "Pane")
    static let caseDisplayRepresentations: [UIPane: DisplayRepresentation] = [
        .library: "Library", .preview: "Preview", .reader: "Reader", .inspector: "Inspector",
        .activity: "Activity", .chat: "Chat", .segments: "Segments"
    ]

    /// By the name a script says; "reading" (the pane kind's own name) is the Reader.
    init?(named name: String) {
        let key = name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        self.init(rawValue: key == "reading" ? "reader" : key)
    }

    /// The pane-list kind, for the panes that are one (Activity is a window; the Inspector a column).
    var paneKind: PaneKind? {
        switch self {
        case .library: .library
        case .preview: .preview
        case .reader: .reading
        case .chat: .chat
        case .segments: .segments
        case .inspector, .activity: nil
        }
    }

    /// The key its frame is recorded under in `WindowState.paneFrames`.
    var frameKey: String { paneKind?.rawValue ?? rawValue }
}

extension InspectorTab {
    /// By the name a script says: the tab's title ("Knowledge Graph") or its case ("knowledgeGraph"), any case.
    init?(named name: String) {
        let key = name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard let tab = Self.allCases.first(where: { $0.rawValue.lowercased() == key || "\($0)".lowercased() == key })
        else { return nil }
        self = tab
    }
}

extension View {
    /// Record where this pane sits in the window, for the screenshot verb (`WindowState.paneFrames`).
    func recordsPaneFrame(_ key: String, in windowState: WindowState) -> some View {
        onGeometryChange(for: CGRect.self) { $0.frame(in: .global) } action: { windowState.paneFrames[key] = $0 }
            .onDisappear { windowState.paneFrames[key] = nil }
    }
}
