// MARK: - Transcript Layout (#3805)

/// How the Reader lays out a transcript (#3805). DIPLOMATIC is the default because
/// the manuscript's line structure is real data and must never be lost silently
/// (the maintainer); READING reflow is opt-in. This is the persisted CHOICE only — the
/// engine reflow rendering and the raw/cleaned text wiring land in separate slices,
/// which read this same `storageKey`. Kept module-accessible (not private) so those
/// slices can reference it; RawRepresentable String so `@AppStorage` stores it.
enum TranscriptLayout: String, CaseIterable, Identifiable {
    /// Preserve the manuscript's original line breaks exactly.
    case diplomatic
    /// Reflow the text to fit the window width — the manuscript lines are not kept.
    case reading

    var id: String { rawValue }

    var label: String {
        switch self {
        case .diplomatic: "Diplomatic (preserve manuscript lines)"
        case .reading: "Reading (reflow to fit)"
        }
    }

    static let storageKey = "fichero.reader.transcriptLayout"
    /// Diplomatic by default — never lose the manuscript line structure silently.
    static let defaultValue = TranscriptLayout.diplomatic
}
