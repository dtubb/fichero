import Foundation
import Observation

/// App-wide clipboard for image EDIT STEPS — Lightroom's Copy/Paste Settings
/// (Daniel, 2026-09-02: "copy the edits on one image and paste them on
/// others").
///
/// It holds the ordered chain operations, not pixels, so pasting is the same
/// non-destructive `PUT /edits` the editor already speaks: the target keeps
/// its own source bytes and simply adopts the recipe. That is why it is a
/// separate holder from the system pasteboard — ⌘C over a picture means "copy
/// the picture", and these two must never fight over one clipboard.
///
/// Deliberately a singleton rather than editor state: the whole point is to
/// copy in one document and paste in another, which means it must outlive the
/// `ImageEditorModel` that filled it. `@Observable` so a toolbar that reads
/// `operations` re-renders the moment a copy lands and its Paste item goes
/// live.
@MainActor
@Observable
final class ImageEditClipboard {
    static let shared = ImageEditClipboard()

    /// The copied chain, in order. Empty when nothing has been copied.
    private(set) var operations: [AnyCodable] = []
    /// Document the steps were copied FROM — shown in the menu so "Paste" can
    /// say what it is about to paste.
    private(set) var sourceDocumentId: String?
    /// Human-readable step count for the menu title.
    var count: Int { operations.count }
    var isEmpty: Bool { operations.isEmpty }

    private init() {}

    /// Copy a chain. An empty chain is still a legal copy — "this image has no
    /// edits" is a state worth pasting, and refusing it would leave the last
    /// copy silently in place and paste the WRONG recipe on the next ⌘V.
    func copy(operations: [AnyCodable], fromDocumentId documentId: String) {
        self.operations = Self.sanitized(operations)
        self.sourceDocumentId = documentId
    }

    func clear() {
        operations = []
        sourceDocumentId = nil
    }

    /// Strip the per-document bookkeeping the engine writes onto a committed
    /// step before it travels to another image.
    ///
    /// `derived_path` names a cached render of THIS document's pixels; carried
    /// across, it would point the target at another file's bytes. The recipe
    /// (`op` + `params` + `page`) is the only portable part.
    nonisolated static func sanitized(_ operations: [AnyCodable]) -> [AnyCodable] {
        operations.map { operation in
            guard var dict = operation.value as? [String: Any] else { return operation }
            dict.removeValue(forKey: "derived_path")
            dict.removeValue(forKey: "created_at")
            return AnyCodable(dict)
        }
    }
}
