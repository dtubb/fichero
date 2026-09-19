@testable import Fichero
import Foundation
import Testing

/// #4833 — the per-sentence editor. `InlineClaimEditor` already existed
/// (reachable from the claim row's "Edit S/V/O…" context menu, #3463); this
/// slice made it reachable from a clickable sentence (KG digest, biography),
/// fixed its save path to go through the audited action via `ClaimStore`
/// instead of a second, un-observed `actionsService.invokeAction` call, and
/// added the subject-entity-picker and date fields the spec's three [PARTIAL]
/// gaps named (`kg.read.edit-unit-is-the-claim`).
///
/// Reads source rather than mounting the view: what these pin IS a
/// source-level property (which call `save()` makes, in what order, under
/// what guard) — same rationale `ClaimStoreRoutingTests` states for itself.
@Suite(.tags(.knowledgeGraph))
struct InlineClaimEditorTests {
    private static func appSource() throws -> String {
        try AppSource.text("Views/Library/ViewModes/Graph/Ontology/Claim/EditClaimSheet.swift")
    }

    /// `InlineClaimEditor`'s OWN `save()` — the LAST of the file's two
    /// (`EditClaimSheet` also has one) — `.last`, not `.dropFirst().first`,
    /// which would return the text BETWEEN the two occurrences (i.e. still
    /// inside `EditClaimSheet`'s body).
    private static func saveBody() throws -> String {
        let source = try appSource()
        let body = try #require(source.components(separatedBy: "private func save() {").last)
        // Bounded by the next method's signature, a structural marker, not a
        // character count.
        let scope = try #require(body.components(separatedBy: "private func trimmedOrNil(").first)
        return AppSource.codeOnly(scope)
    }

    // MARK: - kg.read.editor-saves-through-the-audited-action

    /// The save path is `ClaimStore.patch` — the audited `claim.patch`
    /// action — never a second, bespoke `actionsService.invokeAction` call
    /// bypassing the store (the bug this slice fixed: the old path called
    /// the action directly, discarded its response, and handed `onSave` the
    /// STALE claim it was opened with).
    @Test("save routes through ClaimStore.patch, not a direct action call")
    func saveRoutesThroughTheStore() throws {
        let scope = try Self.saveBody()
        #expect(scope.contains("try await claimStore.patch("))
        #expect(!scope.contains("actionsService.invokeAction("))
    }

    /// `onSave` receives the value `claimStore.patch` RETURNS — the server's
    /// freshly-patched claim — never the `claim` property this editor was
    /// constructed with.
    @Test("onSave is called with the patch response, not the stale claim")
    func onSaveGetsTheUpdatedClaim() throws {
        let scope = try Self.saveBody()
        let patchIndex = try #require(scope.range(of: "try await claimStore.patch("))
        let onSaveIndex = try #require(scope.range(of: "onSave(updated)"))
        #expect(patchIndex.lowerBound < onSaveIndex.lowerBound)
    }

    // MARK: - Subject: entity picker only, never a client-made-up name

    /// `subjectCanonical` is never sent from this editor — the subject field
    /// was replaced with `ClaimSubjectEntityPicker`, which can only produce
    /// an id, and the engine (commit 69fba6090) derives the name itself.
    @Test("save never sends subjectCanonical — the picker only produces an id")
    func saveNeverSendsAGuessedSubjectName() throws {
        let scope = try Self.saveBody()
        #expect(!scope.contains("subjectCanonical:"))
        #expect(scope.contains("subjectEntityId:"))
    }

    /// The subject id is sent only when the picker actually changed it —
    /// re-sending the unchanged id is harmless but this pins the INTENT
    /// (a conditional, not an unconditional pass-through) so a future edit
    /// can't accidentally start sending it unconditionally without the
    /// reader of this test noticing the assertion changed shape.
    @Test("subject_entity_id is sent conditionally, only on a real change")
    func subjectEntityIdSentOnlyWhenChanged() throws {
        let scope = try Self.saveBody()
        #expect(scope.contains("subjectEntityId != claim.subjectEntityId ? subjectEntityId : nil"))
    }

    // MARK: - Date fields (spec gap (c): "the editor has no date field")

    @Test("save sends the date fields the wire already supports")
    func saveSendsDateFields() throws {
        let scope = try Self.saveBody()
        #expect(scope.contains("timeStart: trimmedOrNil(timeStart)"))
        #expect(scope.contains("timeEnd: trimmedOrNil(timeEnd)"))
        #expect(scope.contains("timePrecision: trimmedOrNil(timePrecision)"))
    }

    @Test("the editor's body renders fields for start, end and precision")
    func bodyRendersDateFields() throws {
        let scope = try Self.inlineEditorBody()
        #expect(scope.contains("$timeStart"))
        #expect(scope.contains("$timeEnd"))
        #expect(scope.contains("$timePrecision"))
    }

    // MARK: - Cancel changes nothing

    /// The Cancel button's action is `onCancel` alone — no save call, no
    /// state mutation beyond what the caller's `onCancel` closure does.
    @Test("cancel calls onCancel only — never save")
    func cancelNeverSaves() throws {
        let scope = try Self.inlineEditorBody()
        #expect(scope.contains(#"Button("Cancel", action: onCancel)"#))
    }

    /// Everything from `struct InlineClaimEditor: View {` to the end of the
    /// file — it occurs once, and nothing after it (`ClaimSubjectEntityPicker`)
    /// redefines `save()`/the Cancel button, so no prefix cap is needed.
    private static func inlineEditorBody() throws -> String {
        let source = try appSource()
        let body = try #require(
            source.components(separatedBy: "struct InlineClaimEditor: View {").dropFirst().first
        )
        return AppSource.codeOnly(body)
    }
}
