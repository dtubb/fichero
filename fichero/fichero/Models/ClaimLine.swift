import Foundation

/// How one claim reads in a list that is already grouped under its subject
/// (#4393, part 1).
///
/// Three claims about Adolfo Hurtado rendered as:
///
///     Adolfo Hurtado Adolfo Hurtado Notario público del Circuito de San Juan;
///     Adolfo Hurtado compareció (ante mí) ante él Juan Catarino Asprilla…;
///     Adolfo Hurtado doi fé (que conosco) que conoce a los comparecientes…
///
/// A claim is a triple, and the subject is constant across an entity's digest.
/// Printing it on every line spends the narrowest space in the app on the one
/// word the reader already knows — they are looking at that entity's page.
///
/// The doubled first line has a second cause: when the typed triple is
/// unavailable the composer fell back to `claim.text`, the flattened sentence
/// with the subject embedded — so a fallback row printed the subject once from
/// the composer and once from inside the text.
///
/// **Not a record fix.** The issue asked whether the triple is real before
/// designing this, and it is: `subject_canonical`, `predicate_verb`,
/// `object_phrase` and the `svo_*` fields all persist. The record was fine and
/// the view was discarding it.
///
/// The rule is "omit when it equals the group subject", never "always omit" —
/// a claim about someone else that mentions this entity must still say who it
/// is about, or the list would assert the wrong thing.
enum ClaimLine {

    /// One claim's line, with the subject dropped only when it is redundant.
    ///
    /// - Parameters:
    ///   - subject: the claim's own subject, if the typed triple had one.
    ///   - verb: predicate.
    ///   - object: object phrase.
    ///   - fallback: the flattened `claim.text`, used when there is no triple.
    ///   - groupSubject: the subject the surrounding list is grouped under, or
    ///     `nil` where there is no grouping — a delete confirmation names one
    ///     claim out of context and must keep its subject.
    static func text(
        subject: String?,
        verb: String?,
        object: String?,
        fallback: String,
        groupSubject: String?
    ) -> String {
        let subject = clean(subject)
        let verb = clean(verb)
        let object = clean(object)

        if !verb.isEmpty || !object.isEmpty {
            var parts: [String] = []
            if !subject.isEmpty, !matches(subject, groupSubject) { parts.append(subject) }
            parts.append(contentsOf: [verb, object].filter { !$0.isEmpty })
            let line = parts.joined(separator: " · ")
            if !line.isEmpty { return line }
        }

        return fallbackLine(clean(fallback), groupSubject: groupSubject)
    }

    /// The no-triple path.
    ///
    /// Strips only an **exact leading** occurrence of the group subject. The
    /// issue rightly warns that a subject cannot be reliably stripped from a
    /// sentence in general — so this does not try. It removes the one case it
    /// can be certain about, the prefix that produced the visible doubling, and
    /// leaves every other occurrence alone rather than guessing.
    static func fallbackLine(_ text: String, groupSubject: String?) -> String {
        guard let groupSubject = groupSubject.map(clean), !groupSubject.isEmpty else {
            return text.isEmpty ? placeholder : text
        }
        guard text.lowercased().hasPrefix(groupSubject.lowercased()) else {
            return text.isEmpty ? placeholder : text
        }
        let stripped = clean(String(text.dropFirst(groupSubject.count)))
        // If removing the prefix leaves nothing, the text WAS just the subject:
        // keep the original rather than rendering an empty row.
        return stripped.isEmpty ? text : stripped
    }

    /// Shown when a claim carries neither a triple nor text. An empty row is
    /// indistinguishable from a rendering bug.
    static let placeholder = "Untitled claim"

    /// Subject equality for display purposes: case- and whitespace-insensitive,
    /// because `subject_canonical` and an entity's `canonical_name` are
    /// independently normalised and differ in case more often than in content.
    static func matches(_ subject: String, _ groupSubject: String?) -> Bool {
        guard let groupSubject = groupSubject.map(clean), !groupSubject.isEmpty else { return false }
        return subject.compare(groupSubject, options: [.caseInsensitive, .diacriticInsensitive])
            == .orderedSame
    }

    private static func clean(_ value: String?) -> String {
        (value ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
