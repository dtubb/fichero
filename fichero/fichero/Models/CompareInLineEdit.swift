import Foundation

/// The per-line workbench's rules (`source.editor.compare-two-to-four-readings-with-the-line-picture-and-edit-in-line`, #6462):
/// a comparison takes two to four readings, and an edit of a compared reading is a NEW reading derived from it at its own
/// level and kind, never an overwrite. The view only draws what this says.
enum CompareInLineEdit {
    static let allowed = 2...4

    /// Why a reading cannot be added to the comparison; nil when it can.
    static func refusal(adding count: Int) -> String? {
        count >= allowed.upperBound ? "Compare takes two to four readings." : nil
    }

    /// Whether a comparison of this many readings can be shown.
    static func isComparable(_ count: Int) -> Bool { allowed.contains(count) }

    /// The reading to write when a compared reading is edited and saved.
    struct Correction: Equatable {
        let derivedFromRepresentationId: String
        let level: String?
        let kind: String
        let content: String
    }

    /// The compared reading an edit starts from.
    struct Reading: Equatable {
        let id: String
        let level: String?
        let kind: String
        let text: String
    }

    /// A correction of `reading`'s text, or nil when nothing changed (Save does nothing then).
    static func correction(of reading: Reading, to edited: String) -> Correction? {
        edited == reading.text ? nil : Correction(derivedFromRepresentationId: reading.id, level: reading.level,
                                                  kind: reading.kind, content: edited)
    }
}
