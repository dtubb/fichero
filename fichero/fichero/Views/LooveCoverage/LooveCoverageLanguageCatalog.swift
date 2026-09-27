import SwiftUI

//  Extracted for file_length (#5113). Behaviour unchanged: the declarations below are
//  byte-for-byte what they were, moved so the file they came from stays readable.

// MARK: - Language catalog

/// The languages/scripts the coverage window can show, split into modern and
/// historical. The user picks a subset; the service fetches only the chosen set.
///
/// Historical scripts are the demo-gold — where tokenizers actually diverge. Their
/// query codes are best-effort identifiers the engine's language resolver is
/// gaining exemplars for in parallel; until those land a chosen historical column
/// will honestly read "unknown" for every model (the window never fakes it).
enum LanguageCatalog {
    static let modern: [CoverageLanguage] = [
        CoverageLanguage(code: "en", name: "English"),
        CoverageLanguage(code: "es", name: "Spanish"),
        CoverageLanguage(code: "fr", name: "French"),
        CoverageLanguage(code: "de", name: "German"),
        CoverageLanguage(code: "pt", name: "Portuguese"),
        CoverageLanguage(code: "it", name: "Italian"),
        CoverageLanguage(code: "ru", name: "Russian"),
        CoverageLanguage(code: "uk", name: "Ukrainian"),
        CoverageLanguage(code: "el", name: "Greek"),
        CoverageLanguage(code: "ar", name: "Arabic"),
        CoverageLanguage(code: "he", name: "Hebrew")
    ]

    /// Historical scripts. `ru-petr1708` is the BCP-47 variant subtag for the
    /// pre-1918 Russian orthography; `cop`/`ka`/`hy` are the ISO codes for
    /// Coptic / Georgian / Armenian.
    static let historical: [CoverageLanguage] = [
        CoverageLanguage(code: "ru-petr1708", name: "Russian (pre-1918)"),
        CoverageLanguage(code: "cop", name: "Coptic"),
        CoverageLanguage(code: "ka", name: "Georgian"),
        CoverageLanguage(code: "hy", name: "Armenian")
    ]

    static var all: [CoverageLanguage] { modern + historical }

    /// A broad ISO-639 name↔code list backing the "add any language" search. Each
    /// code is the SHORTEST ISO code — 639-1 (two letters) where one exists, else
    /// 639-3 (three letters). That is exactly the keying Andy Janco's published
    /// loove coverage uses, so a chosen code resolves to his authoritative data
    /// when he has it (~8,000 languages) and to an honest "unknown" when he
    /// doesn't. Not the full sweep — a pragmatic, commonly-encountered set plus a
    /// few notable historical languages; the engine returns unknown, never a
    /// guess, for anything it lacks.
    static let iso: [CoverageLanguage] = [
        CoverageLanguage(code: "aa", name: "Afar"),
        CoverageLanguage(code: "ab", name: "Abkhazian"),
        CoverageLanguage(code: "af", name: "Afrikaans"),
        CoverageLanguage(code: "ak", name: "Akan"),
        CoverageLanguage(code: "am", name: "Amharic"),
        CoverageLanguage(code: "an", name: "Aragonese"),
        CoverageLanguage(code: "ar", name: "Arabic"),
        CoverageLanguage(code: "as", name: "Assamese"),
        CoverageLanguage(code: "av", name: "Avaric"),
        CoverageLanguage(code: "ay", name: "Aymara"),
        CoverageLanguage(code: "az", name: "Azerbaijani"),
        CoverageLanguage(code: "ba", name: "Bashkir"),
        CoverageLanguage(code: "be", name: "Belarusian"),
        CoverageLanguage(code: "bg", name: "Bulgarian"),
        CoverageLanguage(code: "bh", name: "Bihari"),
        CoverageLanguage(code: "bi", name: "Bislama"),
        CoverageLanguage(code: "bm", name: "Bambara"),
        CoverageLanguage(code: "bn", name: "Bengali"),
        CoverageLanguage(code: "bo", name: "Tibetan"),
        CoverageLanguage(code: "br", name: "Breton"),
        CoverageLanguage(code: "bs", name: "Bosnian"),
        CoverageLanguage(code: "ca", name: "Catalan"),
        CoverageLanguage(code: "ce", name: "Chechen"),
        CoverageLanguage(code: "ch", name: "Chamorro"),
        CoverageLanguage(code: "co", name: "Corsican"),
        CoverageLanguage(code: "cr", name: "Cree"),
        CoverageLanguage(code: "cs", name: "Czech"),
        CoverageLanguage(code: "cu", name: "Church Slavonic"),
        CoverageLanguage(code: "cv", name: "Chuvash"),
        CoverageLanguage(code: "cy", name: "Welsh"),
        CoverageLanguage(code: "da", name: "Danish"),
        CoverageLanguage(code: "de", name: "German"),
        CoverageLanguage(code: "dv", name: "Divehi"),
        CoverageLanguage(code: "dz", name: "Dzongkha"),
        CoverageLanguage(code: "ee", name: "Ewe"),
        CoverageLanguage(code: "el", name: "Greek"),
        CoverageLanguage(code: "en", name: "English"),
        CoverageLanguage(code: "eo", name: "Esperanto"),
        CoverageLanguage(code: "es", name: "Spanish"),
        CoverageLanguage(code: "et", name: "Estonian"),
        CoverageLanguage(code: "eu", name: "Basque"),
        CoverageLanguage(code: "fa", name: "Persian"),
        CoverageLanguage(code: "ff", name: "Fulah"),
        CoverageLanguage(code: "fi", name: "Finnish"),
        CoverageLanguage(code: "fj", name: "Fijian"),
        CoverageLanguage(code: "fo", name: "Faroese"),
        CoverageLanguage(code: "fr", name: "French"),
        CoverageLanguage(code: "fy", name: "Western Frisian"),
        CoverageLanguage(code: "ga", name: "Irish"),
        CoverageLanguage(code: "gd", name: "Scottish Gaelic"),
        CoverageLanguage(code: "gl", name: "Galician"),
        CoverageLanguage(code: "gn", name: "Guarani"),
        CoverageLanguage(code: "gu", name: "Gujarati"),
        CoverageLanguage(code: "gv", name: "Manx"),
        CoverageLanguage(code: "ha", name: "Hausa"),
        CoverageLanguage(code: "he", name: "Hebrew"),
        CoverageLanguage(code: "hi", name: "Hindi"),
        CoverageLanguage(code: "ho", name: "Hiri Motu"),
        CoverageLanguage(code: "hr", name: "Croatian"),
        CoverageLanguage(code: "ht", name: "Haitian Creole"),
        CoverageLanguage(code: "hu", name: "Hungarian"),
        CoverageLanguage(code: "hy", name: "Armenian"),
        CoverageLanguage(code: "hz", name: "Herero"),
        CoverageLanguage(code: "ia", name: "Interlingua"),
        CoverageLanguage(code: "id", name: "Indonesian"),
        CoverageLanguage(code: "ig", name: "Igbo"),
        CoverageLanguage(code: "is", name: "Icelandic"),
        CoverageLanguage(code: "it", name: "Italian"),
        CoverageLanguage(code: "iu", name: "Inuktitut"),
        CoverageLanguage(code: "ja", name: "Japanese"),
        CoverageLanguage(code: "jv", name: "Javanese"),
        CoverageLanguage(code: "ka", name: "Georgian"),
        CoverageLanguage(code: "kk", name: "Kazakh"),
        CoverageLanguage(code: "kl", name: "Kalaallisut"),
        CoverageLanguage(code: "km", name: "Khmer"),
        CoverageLanguage(code: "kn", name: "Kannada"),
        CoverageLanguage(code: "ko", name: "Korean"),
        CoverageLanguage(code: "ks", name: "Kashmiri"),
        CoverageLanguage(code: "ku", name: "Kurdish"),
        CoverageLanguage(code: "kw", name: "Cornish"),
        CoverageLanguage(code: "ky", name: "Kyrgyz"),
        CoverageLanguage(code: "la", name: "Latin"),
        CoverageLanguage(code: "lb", name: "Luxembourgish"),
        CoverageLanguage(code: "lg", name: "Ganda"),
        CoverageLanguage(code: "ln", name: "Lingala"),
        CoverageLanguage(code: "lo", name: "Lao"),
        CoverageLanguage(code: "lt", name: "Lithuanian"),
        CoverageLanguage(code: "lv", name: "Latvian"),
        CoverageLanguage(code: "mg", name: "Malagasy"),
        CoverageLanguage(code: "mi", name: "Maori"),
        CoverageLanguage(code: "mk", name: "Macedonian"),
        CoverageLanguage(code: "ml", name: "Malayalam"),
        CoverageLanguage(code: "mn", name: "Mongolian"),
        CoverageLanguage(code: "mr", name: "Marathi"),
        CoverageLanguage(code: "ms", name: "Malay"),
        CoverageLanguage(code: "mt", name: "Maltese"),
        CoverageLanguage(code: "my", name: "Burmese"),
        CoverageLanguage(code: "na", name: "Nauru"),
        CoverageLanguage(code: "nb", name: "Norwegian Bokmål"),
        CoverageLanguage(code: "ne", name: "Nepali"),
        CoverageLanguage(code: "nl", name: "Dutch"),
        CoverageLanguage(code: "nn", name: "Norwegian Nynorsk"),
        CoverageLanguage(code: "no", name: "Norwegian"),
        CoverageLanguage(code: "ny", name: "Chichewa"),
        CoverageLanguage(code: "oc", name: "Occitan"),
        CoverageLanguage(code: "om", name: "Oromo"),
        CoverageLanguage(code: "or", name: "Odia"),
        CoverageLanguage(code: "os", name: "Ossetian"),
        CoverageLanguage(code: "pa", name: "Punjabi"),
        CoverageLanguage(code: "pl", name: "Polish"),
        CoverageLanguage(code: "ps", name: "Pashto"),
        CoverageLanguage(code: "pt", name: "Portuguese"),
        CoverageLanguage(code: "qu", name: "Quechua"),
        CoverageLanguage(code: "rm", name: "Romansh"),
        CoverageLanguage(code: "rn", name: "Rundi"),
        CoverageLanguage(code: "ro", name: "Romanian"),
        CoverageLanguage(code: "ru", name: "Russian"),
        CoverageLanguage(code: "rw", name: "Kinyarwanda"),
        CoverageLanguage(code: "sa", name: "Sanskrit"),
        CoverageLanguage(code: "sd", name: "Sindhi"),
        CoverageLanguage(code: "se", name: "Northern Sami"),
        CoverageLanguage(code: "sg", name: "Sango"),
        CoverageLanguage(code: "si", name: "Sinhala"),
        CoverageLanguage(code: "sk", name: "Slovak"),
        CoverageLanguage(code: "sl", name: "Slovenian"),
        CoverageLanguage(code: "sm", name: "Samoan"),
        CoverageLanguage(code: "sn", name: "Shona"),
        CoverageLanguage(code: "so", name: "Somali"),
        CoverageLanguage(code: "sq", name: "Albanian"),
        CoverageLanguage(code: "sr", name: "Serbian"),
        CoverageLanguage(code: "ss", name: "Swati"),
        CoverageLanguage(code: "st", name: "Southern Sotho"),
        CoverageLanguage(code: "su", name: "Sundanese"),
        CoverageLanguage(code: "sv", name: "Swedish"),
        CoverageLanguage(code: "sw", name: "Swahili"),
        CoverageLanguage(code: "ta", name: "Tamil"),
        CoverageLanguage(code: "te", name: "Telugu"),
        CoverageLanguage(code: "tg", name: "Tajik"),
        CoverageLanguage(code: "th", name: "Thai"),
        CoverageLanguage(code: "ti", name: "Tigrinya"),
        CoverageLanguage(code: "tk", name: "Turkmen"),
        CoverageLanguage(code: "tl", name: "Tagalog"),
        CoverageLanguage(code: "tn", name: "Tswana"),
        CoverageLanguage(code: "to", name: "Tongan"),
        CoverageLanguage(code: "tr", name: "Turkish"),
        CoverageLanguage(code: "ts", name: "Tsonga"),
        CoverageLanguage(code: "tt", name: "Tatar"),
        CoverageLanguage(code: "ug", name: "Uyghur"),
        CoverageLanguage(code: "uk", name: "Ukrainian"),
        CoverageLanguage(code: "ur", name: "Urdu"),
        CoverageLanguage(code: "uz", name: "Uzbek"),
        CoverageLanguage(code: "ve", name: "Venda"),
        CoverageLanguage(code: "vi", name: "Vietnamese"),
        CoverageLanguage(code: "wo", name: "Wolof"),
        CoverageLanguage(code: "xh", name: "Xhosa"),
        CoverageLanguage(code: "yi", name: "Yiddish"),
        CoverageLanguage(code: "yo", name: "Yoruba"),
        CoverageLanguage(code: "zh", name: "Chinese"),
        CoverageLanguage(code: "zu", name: "Zulu"),
        // Notable historical / classical languages (639-3), where tokenizers most
        // often diverge — the loove demo-gold beyond the curated set above.
        CoverageLanguage(code: "cop", name: "Coptic"),
        CoverageLanguage(code: "grc", name: "Ancient Greek"),
        CoverageLanguage(code: "ang", name: "Old English"),
        CoverageLanguage(code: "got", name: "Gothic"),
        CoverageLanguage(code: "syc", name: "Classical Syriac"),
        CoverageLanguage(code: "chu", name: "Old Church Slavonic"),
        CoverageLanguage(code: "arc", name: "Aramaic")
    ]

    /// Every language the searchable picker can offer: curated (modern +
    /// historical) FIRST, then the broader ISO list, de-duplicated by code so a
    /// curated entry (with its richer name / variant tag) wins.
    static let searchable: [CoverageLanguage] = {
        var seen = Set<String>()
        var out: [CoverageLanguage] = []
        for language in all + iso where seen.insert(language.code).inserted {
            out.append(language)
        }
        return out
    }()

    /// Default visible set — a mix that INCLUDES historical scripts so the
    /// differences show the moment the window opens.
    static let defaultSelectedCodes: [String] = ["en", "es", "ru", "ru-petr1708", "el", "cop"]

    /// Filter the searchable catalog by a free-text query matching name OR code
    /// (case-insensitive). An empty query returns the whole catalog.
    static func search(_ query: String) -> [CoverageLanguage] {
        let needle = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !needle.isEmpty else { return searchable }
        return searchable.filter {
            $0.name.lowercased().contains(needle) || $0.code.lowercased().contains(needle)
        }
    }

    /// Resolve a code to a display language: a searchable-catalog entry if we know
    /// it, else an honest passthrough (the code, upper-cased, as its own name) so
    /// an arbitrary chosen code the engine may or may not score still shows as its
    /// own column rather than vanishing.
    static func language(for code: String) -> CoverageLanguage {
        searchable.first { $0.code == code }
            ?? CoverageLanguage(code: code, name: code.uppercased())
    }

    /// Languages for the chosen codes in a STABLE order: searchable-catalog order
    /// (curated then ISO) first, then any remaining off-catalog codes sorted, so
    /// columns never reshuffle and a freely-chosen code is never dropped — the old
    /// behavior silently discarded any code outside `all`.
    static func languages(for codes: Set<String>) -> [CoverageLanguage] {
        var remaining = codes
        var out: [CoverageLanguage] = []
        for language in searchable where remaining.remove(language.code) != nil {
            out.append(language)
        }
        out += remaining.sorted().map { CoverageLanguage(code: $0, name: $0.uppercased()) }
        return out
    }

    /// The chosen codes as a stable, de-duplicated, catalog-ordered list for
    /// @AppStorage persistence — including any freely-chosen off-catalog codes.
    static func orderedCodes(_ codes: Set<String>) -> [String] {
        languages(for: codes).map(\.code)
    }
}
