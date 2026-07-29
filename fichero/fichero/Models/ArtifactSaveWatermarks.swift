import Foundation

/// Pure state machine for the artifact / page-content editor's save
/// watermarks (#2478 self-echo suppression + #4285 failed-save dirtiness).
///
/// The editor keeps two watermarks:
///  - `lastSavedEncoded`: canonical encoded form of the last seeded or
///    successfully saved content — a draft equal to it is CLEAN (no save
///    needed); anything else is DIRTY.
///  - `lastLoadedRaw`: the raw stored content the editor last seeded from —
///    guards the `.task(id:)` reseed against our own save echoing back.
///
/// The #4285 data-loss bug: both watermarks were advanced BEFORE the save
/// round-trip and never rolled back on failure, so a rejected save left the
/// draft looking clean — no retry ever fired, and the next reseed replaced
/// the buffer with the stale stored content, silently discarding the paste.
/// `beginSave`/`rollBack` make that transaction explicit and testable.
struct ArtifactSaveWatermarks: Equatable {
    var lastSavedEncoded: String = ""
    var lastLoadedRaw: String = ""

    /// True when `encoded` matches the last seeded/saved content — nothing
    /// to persist.
    func isClean(encoded: String) -> Bool {
        encoded == lastSavedEncoded
    }

    /// True when the stored content changed externally and the editor should
    /// reseed its draft from it. Our own save echoing back compares equal to
    /// `lastLoadedRaw` and is skipped (#2478).
    func shouldReseed(from raw: String) -> Bool {
        lastLoadedRaw != raw
    }

    /// Seed the editor from stored content (initial load / external update).
    mutating func seed(raw: String, encoded: String) {
        lastLoadedRaw = raw
        lastSavedEncoded = encoded
    }

    /// Optimistically advance both watermarks for an in-flight save (the
    /// echo can race ahead of the response) and return the prior state so a
    /// FAILED save can `rollBack` and leave the draft dirty (#4285).
    mutating func beginSave(encoded: String) -> ArtifactSaveWatermarks {
        let prior = self
        lastSavedEncoded = encoded
        lastLoadedRaw = encoded
        return prior
    }

    /// The save failed — the server never accepted the content, no echo is
    /// coming. Restore the pre-save watermarks so the draft reads as dirty
    /// and every later save path retries the same content.
    mutating func rollBack(to prior: ArtifactSaveWatermarks) {
        self = prior
    }
}
