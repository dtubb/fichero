import SwiftUI

// MARK: - loove coverage domain model
//
// Plain Swift value types the coverage window renders. `LooveCoverageService`
// maps the generated OpenAPI response (`Components.Schemas.LanguageCoverageRecord`
// et al.) into these, so the view layer never touches generator-named types and
// the matrix stays honest about missing data — a `nil` score renders "—", never a
// fabricated number.

/// Qualitative coverage band from the engine's `score_band` enum. `.unknown`
/// absorbs a missing / unrecognized band so the UI always has a color to show.
enum CoverageBand: String, CaseIterable, Sendable {
    case excellent
    case good
    case limited
    case poor
    case unknown

    /// Map the generated string enum's raw value (or `nil`) onto a band.
    init(rawBand: String?) {
        self = CoverageBand(rawValue: rawBand ?? "") ?? .unknown
    }

    /// Semantic color for the band. Green→blue→orange→red descending quality;
    /// gray for unknown. Used for the score text and the header legend.
    var color: Color {
        switch self {
        case .excellent: return .green
        case .good: return .blue
        case .limited: return .orange
        case .poor: return .red
        case .unknown: return .secondary
        }
    }

    var label: String {
        switch self {
        case .excellent: return "Excellent"
        case .good: return "Good"
        case .limited: return "Limited"
        case .poor: return "Poor"
        case .unknown: return "Unknown"
        }
    }
}

/// The four LOOVE tokenizer tiers — how a script's characters are reachable by a
/// model's tokenizer. Tier 0 is best (native single-char tokens), Tier 3 worst
/// (unreachable). Drives the 4-segment bar in every cell and the legend.
enum CoverageTier: Int, CaseIterable, Sendable {
    case native = 0        // Tier 0 — native single-character tokens
    case embedded = 1      // Tier 1 — embedded in multi-character tokens
    case byteFallback = 2  // Tier 2 — byte-fallback tokens
    case unreachable = 3   // Tier 3 — not reachable by the tokenizer

    var color: Color {
        switch self {
        case .native: return .green
        case .embedded: return .teal
        case .byteFallback: return .orange
        case .unreachable: return .red
        }
    }

    var shortLabel: String {
        switch self {
        case .native: return "Tier 0 · native"
        case .embedded: return "Tier 1 · embedded"
        case .byteFallback: return "Tier 2 · byte"
        case .unreachable: return "Tier 3 · unreachable"
        }
    }
}

/// Per-cell tier counts (exemplar-character histogram). `count(for:)` lets the
/// bar iterate `CoverageTier.allCases` without a switch at each call site.
struct CoverageTierCounts: Equatable, Sendable {
    var native: Int
    var embedded: Int
    var byteFallback: Int
    var unreachable: Int

    var total: Int { native + embedded + byteFallback + unreachable }
    var isEmpty: Bool { total == 0 }

    func count(for tier: CoverageTier) -> Int {
        switch tier {
        case .native: return native
        case .embedded: return embedded
        case .byteFallback: return byteFallback
        case .unreachable: return unreachable
        }
    }
}

/// How much to trust a cell's number. THE honesty axis of this window — a tool
/// about tokenizer coverage must never present a per-script guess as a
/// measurement.
///
/// - `derived`: real tokenizer-derived coverage (`source.kind ==
///   loove_derived_json`, `status == derived`). Full confidence — band color.
/// - `heuristic`: the engine's model-independent per-SCRIPT fallback guess
///   (`heuristic_fallback`). Rendered muted with a "~"/"est." marker, NEVER the
///   confident band color.
/// - `unknown`: no score, or no tokenizer to measure (e.g. Apple), or
///   `source.kind == missing`. Rendered "—".
enum CoverageConfidence: Sendable {
    case derived
    case heuristic
    case unknown
}

/// One (model × language) coverage result. `coverageScore == nil` and
/// `tierCounts == nil` are legitimate ("we have no derived data yet") and render
/// as "—".
struct CoverageCell: Identifiable, Equatable, Sendable {
    var provider: String
    var model: String
    var coverageScore: Double?
    var band: CoverageBand
    var tierCounts: CoverageTierCounts?
    var tokensPerChar: Double?
    /// Raw engine status: `derived` / `heuristic` / `unsupported_language` /
    /// `invalid_coverage_file`. Feeds `confidence` and the cell tooltip.
    var status: String
    /// Raw `source.kind`: `loove_derived_json` / `heuristic_fallback` / `missing`.
    /// The authority for whether the score was measured or guessed.
    var sourceKind: String

    var id: String { "\(provider)/\(model)" }

    /// Whether the number was MEASURED, GUESSED, or is absent. `source.kind` is
    /// the authority; a nil score is always unknown regardless of status.
    var confidence: CoverageConfidence {
        guard coverageScore != nil else { return .unknown }
        switch sourceKind {
        case "loove_derived_json":
            // Only a `derived` status confirms the measurement; any other status
            // on a derived file (e.g. invalid) drops to a guess, never full trust.
            return status == "derived" ? .derived : .heuristic
        case "heuristic_fallback":
            return .heuristic
        default: // "missing" or anything unrecognized
            return .unknown
        }
    }
}

/// A language column in the matrix.
struct CoverageLanguage: Identifiable, Equatable, Sendable {
    var code: String
    var name: String

    var id: String { code }
}

/// A model row: its cells keyed by language code. A language with no record for
/// this model simply has no entry — the view shows "—" there.
struct CoverageModelRow: Identifiable, Equatable, Sendable {
    var provider: String
    var model: String
    var cellsByLanguage: [String: CoverageCell]

    var id: String { "\(provider)/\(model)" }
}

/// The assembled matrix: languages (columns) × model rows.
struct CoverageMatrix: Equatable, Sendable {
    var languages: [CoverageLanguage]
    var rows: [CoverageModelRow]

    var isEmpty: Bool { rows.isEmpty }
}

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
