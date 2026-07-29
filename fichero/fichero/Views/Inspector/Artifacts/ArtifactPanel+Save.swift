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
        guard !watermarks.isClean(encoded: ArtifactRichTextCodec.encodeAttributed(draftText)) else { return }
        // A fresh user edit resets the failed-save retry budget (#4285).
        saveRetryAttempts = 0
        autoSaveTask?.cancel()
        autoSaveTask = Task { @MainActor in
            try? await Task.sleep(for: .milliseconds(800))
            if Task.isCancelled { return }
            await performSave()
        }
    }

    /// Bounded auto-retry after a FAILED save (#4285): the draft is still
    /// dirty (watermarks were rolled back), so re-running `performSave`
    /// re-attempts the identical content. Capped at `maxSaveRetries`; beyond
    /// that the error stays visible and the next edit / blur / flush retries.
    static let maxSaveRetries = 3

    func scheduleFailedSaveRetry() {
        guard saveRetryAttempts < Self.maxSaveRetries else { return }
        saveRetryAttempts += 1
        autoSaveTask?.cancel()
        autoSaveTask = Task { @MainActor in
            try? await Task.sleep(for: .seconds(2))
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
    func performSave() async {
        guard let onSave else { return }
        await saver.run {
            let encoded = ArtifactRichTextCodec.encodeAttributed(draftText)
            // Nothing changed since the last seed/save — skip the PUT so the
            // coalescing loop terminates once the draft is clean.
            guard !watermarks.isClean(encoded: encoded) else { return }
            // Advance BOTH watermarks before the round-trip: `lastSavedEncoded`
            // so a later onChange doesn't re-fire, and `lastLoadedRaw` so the
            // engine echoing the saved content back through `rawArtifactContent`
            // short-circuits the `.task(id:)` reseed instead of resetting the
            // cursor (#2478). Self-echo suppression in DocumentStore handles the
            // page-content path; this covers artifacts too.
            let prior = watermarks.beginSave(encoded: encoded)
            if let errorMessage = await onSave(encoded) {
                // FAILED save (#4285/#4286): the server never accepted the
                // content, so no echo is coming — roll BOTH watermarks back so
                // the draft reads as DIRTY again. That makes every later path
                // (auto-save onChange, blur flush, store-driven flush, and the
                // bounded retry below) re-attempt the same content instead of
                // treating it as saved and discarding it on the next reseed.
                watermarks.rollBack(to: prior)
                saveError = errorMessage
                scheduleFailedSaveRetry()
            } else {
                saveError = nil
                saveRetryAttempts = 0
            }
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
