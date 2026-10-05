import FicheroAPIClient
import Foundation

/// The Debug-only verb that reaches BELOW a document (#5194, `ui-testing.drive-below-a-document`):
/// `select segment`, answering whether the request was accepted. It goes through the sidebar's reveal
/// (which also lands a segment, as a citable reference does) -- never a second path. Opening a page and
/// showing a pane are the user dictionary's UI verbs now (`open node`, `show pane`, #5453). The rules
/// are here, pure; the command class is `#if DEBUG`.
enum DebugScriptVerbs {
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

#endif
