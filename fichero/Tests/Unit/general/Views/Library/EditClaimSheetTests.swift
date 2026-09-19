@testable import Fichero
import Foundation
import Testing

/// #4833 slice C: `EditClaimSheet` (the full-sheet editor) had the SAME
/// bypass bug `InlineClaimEditor` had before slice B — it called
/// `actionsService.invokeAction(name: "claim.patch", ...)` directly,
/// discarded the response, and never called its own `onSave` at all. Fixed
/// to route through `ClaimStore.patch` — the audited action, same as the
/// inline editor — and hand `onSave` the RETURNED claim.
///
/// Reads source rather than mounting the view, same rationale
/// `ClaimStoreRoutingTests`/`InlineClaimEditorTests` state for themselves:
/// what these pin is a source-level property (which call `save()` makes).
@Suite(.tags(.knowledgeGraph))
struct EditClaimSheetTests {
    private static func appSource() throws -> String {
        try AppSource.text("Views/Library/ViewModes/Graph/Ontology/Claim/EditClaimSheet.swift")
    }

    /// `EditClaimSheet`'s OWN `save()` — the FIRST of the file's two
    /// (`InlineClaimEditor` has the other). `.components(separatedBy:)`
    /// with `.first` after `.dropFirst()` on the SECOND occurrence would
    /// return the text between them — using the split's FIRST tail instead
    /// (there's exactly one `private func save() {` before it) is what
    /// actually isolates this type's own body.
    private static func saveBody() throws -> String {
        let source = try appSource()
        let body = try #require(
            source.components(separatedBy: "private func save() {").dropFirst().first
        )
        // Bounded by the next method's signature, a structural marker.
        let scope = try #require(body.components(separatedBy: "private func trimmedOrNil(").first)
        return AppSource.codeOnly(scope)
    }

    @Test("save routes through ClaimStore.patch, not a direct action call")
    func saveRoutesThroughTheStore() throws {
        let scope = try Self.saveBody()
        #expect(scope.contains("try await claimStore.patch("))
        #expect(!scope.contains("actionsService.invokeAction("))
        #expect(!scope.contains("LibraryManager.shared.getLibrary("))
    }

    /// `onSave` is called at all now (it never was before), and with the
    /// value `claimStore.patch` RETURNS.
    @Test("onSave is called with the patch response")
    func onSaveGetsTheUpdatedClaim() throws {
        let scope = try Self.saveBody()
        let patchIndex = try #require(scope.range(of: "try await claimStore.patch("))
        let onSaveIndex = try #require(scope.range(of: "onSave(updated)"))
        #expect(patchIndex.lowerBound < onSaveIndex.lowerBound)
    }

    /// The now-dead direct-action helper type is gone, not left behind
    /// unused.
    @Test("the direct-action params type no longer exists")
    func actionParamsTypeIsGone() throws {
        let source = try Self.appSource()
        #expect(!source.contains("struct ClaimPatchActionParams"))
    }
}
