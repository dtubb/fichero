import SwiftUI

extension ArtifactPanel {
    // MARK: - Edit mode helpers

    /// Debounced auto-save. The previous explicit Save button created a
    /// "did my edit save?" anxiety loop — auto-save with a small visible
    /// indicator is calmer. (User feedback 2026-04-26.)
    func scheduleAutoSave() {
        // Distinguish a real user edit from a programmatic reseed (load /
        // remote update): only the former changes the encoded form away from
        // the last seeded/saved watermark. Without this, seeding draftText in
        // `.task(id:)` would trip `onChange` and trigger a spurious save.
        guard ArtifactRichTextCodec.encodeAttributed(draftText) != lastSavedEncoded else { return }
        autoSaveTask?.cancel()
        autoSaveTask = Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(800))
            if Task.isCancelled { return }
            await performSave()
        }
    }

    func flushAutoSave() async {
        autoSaveTask?.cancel()
        autoSaveTask = nil
        await performSave()
    }

    /// Persist the latest draft through the serial + coalescing `saver`. A flush
    /// on blur/close *during* an in-flight save is coalesced — the running loop
    /// re-encodes and persists the newest `draftText` before returning — instead
    /// of hitting the old `!isSaving` early-return and silently dropping the
    /// trailing keystrokes (#2536). The coalescing mechanics live in
    /// `CoalescingSaveRunner` so the race is unit-testable.
    private func performSave() async {
        guard let onSave else { return }
        await saver.run {
            let encoded = ArtifactRichTextCodec.encodeAttributed(draftText)
            // Nothing changed since the last seed/save — skip the PUT so the
            // coalescing loop terminates once the draft is clean.
            guard encoded != lastSavedEncoded else { return }
            // Advance BOTH watermarks before the round-trip: `lastSavedEncoded`
            // so a later onChange doesn't re-fire, and `lastLoadedRaw` so the
            // engine echoing the saved content back through `rawArtifactContent`
            // short-circuits the `.task(id:)` reseed instead of resetting the
            // cursor (#2478). Self-echo suppression in DocumentStore handles the
            // page-content path; this covers artifacts too.
            lastSavedEncoded = encoded
            lastLoadedRaw = encoded
            await onSave(encoded)
        }
    }

    /// Raw content used when seeding the editor — for `.artifact` we use the
    /// content field as the editor source, even if it's RTF, so formatting
    /// round-trips. For `.pageContent` we don't have access to the document's
    /// metadata-stored RTF here (we'd need to plumb it through), so plain
    /// text is the editable surface.
    var rawArtifactContent: String {
        switch kind {
        case .pageContent(let text): return text
        case .artifact(let artifact): return artifact.content ?? ""
        }
    }
}
