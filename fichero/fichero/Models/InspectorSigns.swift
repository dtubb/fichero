import Foundation

/// The Inspector's Signs section (`build-notes-inspector.md` 5.6; `source.sign.declared`,
/// `list-authority`, `gather-instances`): the project's declared signs that THIS segment uses or was
/// declared from, each with its name, its character or list number, and how often the project uses
/// it. On a character segment it also shows the letterform, read-only: character › allograph › hand,
/// then the features (`source.letterform.chain`, `features`) -- inside Signs, where the spec puts a
/// character's form, until the maintainer rules whether letterforms want a section of their own.
/// Pure: the words live where a test can reach them.
enum InspectorSigns {
    struct ListReference: Equatable {
        let authority: String
        let number: String
    }

    struct Sign: Equatable, Identifiable {
        let id: String
        let name: String
        /// The segment the sign was declared from: its picture is that segment's.
        let pictureSegmentId: String
        /// "U+F1AC", or nil for a sign known only by a list number.
        let codePoint: String?
        var listReferences: [ListReference] = []
        var variantOf: String?
        var variant: String?
    }

    struct Row: Equatable, Identifiable {
        let signId: String
        /// The sign's name.
        let title: String
        /// "U+F1AC · MUFI F1AC · 1 here · declared from this segment".
        let detail: String
        /// The character itself, when it has one -- drawn by the font, or not at all (a picture where
        /// no font has it is `source.sign.shown-as-picture`, not built).
        let glyph: String?
        var id: String { signId }
    }

    /// "U+F1AC" as the character, or nil when it is not a code point.
    static func character(of codePoint: String?) -> String? {
        guard let codePoint, codePoint.hasPrefix("U+"), let value = UInt32(codePoint.dropFirst(2), radix: 16),
              let scalar = Unicode.Scalar(value) else { return nil }
        return String(Character(scalar))
    }

    /// The signs this segment USES (its counting reading has the character) or was DECLARED FROM, in
    /// the list's order. `usedInProject` is each sign's total across the project, when known.
    static func rows(
        signs: [Sign], segmentId: String, reading: String?, usedInProject: [String: Int] = [:]
    ) -> [Row] {
        signs.compactMap { sign in
            let glyph = character(of: sign.codePoint)
            let here = glyph.map { mark in reading?.unicodeScalars.filter { String($0) == mark }.count ?? 0 } ?? 0
            let declaredHere = sign.pictureSegmentId == segmentId
            guard here > 0 || declaredHere else { return nil }
            var parts: [String] = []
            if let codePoint = sign.codePoint { parts.append(codePoint) }
            parts += sign.listReferences.map { "\($0.authority) \($0.number)" }
            if let base = sign.variantOf { parts.append("a variant of \(base)" + (sign.variant.map { " (\($0))" } ?? "")) }
            if here > 0 { parts.append("\(here) here") }
            if let total = usedInProject[sign.id] { parts.append("\(total) in the project") }
            if declaredHere { parts.append("declared from this segment") }
            return Row(signId: sign.id, title: sign.name, detail: parts.joined(separator: " · "), glyph: glyph)
        }
    }

    struct Letterform: Equatable, Identifiable {
        let id: String
        let character: String
        var allographId: String?
        var handId: String?
        var features: [(component: String, feature: String)] = []
        var describedBy: String?

        static func == (lhs: Self, rhs: Self) -> Bool {
            lhs.id == rhs.id && lhs.character == rhs.character && lhs.allographId == rhs.allographId
                && lhs.handId == rhs.handId && lhs.describedBy == rhs.describedBy
                && lhs.features.map(\.component) == rhs.features.map(\.component)
                && lhs.features.map(\.feature) == rhs.features.map(\.feature)
        }
    }

    struct LetterformLine: Equatable, Identifiable {
        let descriptionId: String
        /// "ܐ › Estrangela alaph › hand B".
        let chain: String
        /// "stem wedged · foot curved · by owner".
        let detail: String
        var id: String { descriptionId }
    }

    /// A letterform in words: the chain from the character to the scribe's hand, then its features.
    static func lines(_ letterforms: [Letterform], allographs: [String: String], hands: [String: String]) -> [LetterformLine] {
        letterforms.map { form in
            var chain = [form.character]
            if let id = form.allographId { chain.append(allographs[id] ?? "an unlisted allograph") }
            if let id = form.handId { chain.append(hands[id] ?? "an unlisted hand") }
            var parts = form.features.map { "\($0.component) \($0.feature)" }
            if let author = form.describedBy { parts.append("by \(author)") }
            return LetterformLine(
                descriptionId: form.id, chain: chain.joined(separator: " › "), detail: parts.joined(separator: " · ")
            )
        }
    }
}
