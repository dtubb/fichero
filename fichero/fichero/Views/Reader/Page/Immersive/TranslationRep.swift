import Foundation

/// A loaded translation representation of the current page (#3329): the target
/// language code + the translated text (from a `translation` artifact whose
/// `data.target_lang` records the language).
struct TranslationRep: Identifiable {
    let lang: String
    let content: String
    /// Provenance (#3325 step 4): the model that produced it, and whether a
    /// human has reviewed it.
    let provider: String?
    let model: String?
    let reviewed: Bool
    var id: String { lang }
    /// Human name, e.g. "Spanish" for "es"; falls back to the raw code.
    var displayName: String {
        Locale.current.localizedString(forLanguageCode: lang)?.capitalized
            ?? lang.uppercased()
    }
    /// One-line provenance: "provider · model", omitting blanks.
    var provenance: String {
        [provider, model].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · ")
    }
}
