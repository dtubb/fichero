import FicheroAPIClient
import Foundation

/// The Debug-only verbs that reach BELOW a document (#5194, `ui-testing.drive-below-a-document`):
/// `select page`, `select segment`, `show pane`. Each answers whether the request was accepted, in the
/// style of `select document` / `show panel`, and goes through a seam the app already has -- the
/// sidebar's reveal (which also lands a segment, as a citable reference does) and the pane list's
/// visibility -- never a second path. The rules are here, pure; the command classes are `#if DEBUG`.
enum DebugScriptVerbs {
    /// A pane kind by the name a script uses ("segments", "preview", ...); nil for anything else.
    static func paneKind(named name: String) -> PaneKind? {
        PaneKind(rawValue: name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
    }

    /// The names `show pane` accepts, for a refusal that says what would have worked.
    static var paneNames: [String] { PaneKind.allCases.map(\.rawValue) }

    /// What the sidebar's reveal is told: the page, and the segment to select once it is shown.
    static func revealUserInfo(documentId: String, segmentId: String? = nil) -> [String: String] {
        var info = ["documentId": documentId]
        if let segmentId { info["segmentId"] = segmentId }
        return info
    }

    /// The live page and segment for a segment id in the OPEN library, through the engine's one resolver
    /// (it follows a merge or a split), as `[documentId, segmentId]`; nil when no library is open or the
    /// segment was deleted with no successor.
    @MainActor
    static func landingInOpenLibrary(forSegment segmentId: String) async throws -> [String]? {
        let manager = LibraryManager.shared
        guard let library = manager.openLibraries.first(where: { $0.id == manager.currentLibraryId }) else { return nil }
        let locations = LocationService(ficheroClient: library.segmentService.client)
        let resolved = try await locations.resolve(Components.Schemas.Location(segmentId: segmentId))
        return SegmentReference.landing(resolved).map { [$0.documentId, $0.segmentId] }
    }
}

#if DEBUG && os(macOS)  // AppleScript commands (NSScriptCommand) exist only on the Mac
/// `select page <document id>` (Debug test suite): the page opened in the Library, as a click opens it.
@objc(FicheroSelectPageCommand)
class FicheroSelectPageCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        guard let documentId = directParameter as? String, !documentId.isEmpty else {
            scriptErrorNumber = NSRequiredArgumentsMissingScriptError
            scriptErrorString = "Page (document) id is required"
            return false
        }
        NotificationCenter.default.post(
            name: .sidebarRevealDocument, object: nil, userInfo: DebugScriptVerbs.revealUserInfo(documentId: documentId)
        )
        return true
    }
}

/// `select segment <segment id>` (Debug test suite): its page opened and the segment selected -- the one
/// selection the Source view, the Reader and the Inspector share. False when it does not resolve.
@objc(FicheroSelectSegmentCommand)
class FicheroSelectSegmentCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        guard let segmentId = directParameter as? String, !segmentId.isEmpty else {
            scriptErrorNumber = NSRequiredArgumentsMissingScriptError
            scriptErrorString = "Segment id is required"
            return false
        }
        do {
            let landing = try runAsyncWithoutBlocking {
                try await DebugScriptVerbs.landingInOpenLibrary(forSegment: segmentId)
            }
            guard let landing else {
                scriptErrorNumber = NSInternalScriptError
                scriptErrorString = "Segment \(segmentId) is not in the open library, or was deleted with no successor"
                return false
            }
            NotificationCenter.default.post(
                name: .sidebarRevealDocument, object: nil,
                userInfo: DebugScriptVerbs.revealUserInfo(documentId: landing[0], segmentId: landing[1])
            )
            return true
        } catch {
            scriptErrorNumber = NSInternalScriptError
            scriptErrorString = error.localizedDescription
            return false
        }
    }
}

/// `show pane <name>` (Debug test suite): a pane of that kind shown in the window's pane list, added when
/// absent (`PaneList.settingVisible`). False for a name that is not a pane kind.
@objc(FicheroShowPaneCommand)
class FicheroShowPaneCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        guard let name = directParameter as? String, let kind = DebugScriptVerbs.paneKind(named: name) else {
            scriptErrorNumber = NSArgumentsWrongScriptError
            scriptErrorString = "Not a pane: \(directParameter ?? "nothing"). Panes: "
                + DebugScriptVerbs.paneNames.joined(separator: ", ")
            return false
        }
        NotificationCenter.default.post(name: .ficheroShowPanelRequested, object: nil, userInfo: ["pane": kind.rawValue])
        return true
    }
}
#endif
