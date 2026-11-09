import Foundation

/// The one small label on a line's shown text (#6455, `source.editor.the-shown-reading-is-the-counting-one-and-says-so`):
/// "<reader or person> · <level>" and a basis glyph, the basis words for the tooltip. Built from the line's readings, so the
/// Reader's Lines row says the same thing the Inspector's Text section does.
struct ShownReadingLabel: Equatable {
    let text: String
    let glyph: String
    let help: String
    /// The reading the line SHOWS: the counting one, else (none counts) the newest person's, else the newest.
    let shown: InspectorText.Reading

    init?(_ text: InspectorText?, kind: String = "transcription") {
        guard let text else { return nil }
        let all = text.readings(ofKind: kind)
        let counted = text.countingReading(ofKind: kind)
        let newestFirst = all.sorted { ($0.createdAt ?? .distantPast) > ($1.createdAt ?? .distantPast) }
        guard let shown = counted ?? newestFirst.first(where: { $0.maker == "human" }) ?? newestFirst.first else { return nil }
        self.shown = shown
        let basis: InspectorText.Why = counted == nil ? .noneCounts : (text.counting[kind]?.why ?? .noneCounts)
        help = basis.label
        switch basis {
        case .chosen: glyph = "checkmark"
        case .newestHuman, .correction: glyph = "person"
        case .newestMachineUnchosen: glyph = "circle"
        case .noneCounts: glyph = "minus"
        case .unknown: glyph = "questionmark"
        }
        if basis == .noneCounts, all.count > 1 {
            self.text = "\(all.count) readings, none chosen"
        } else {
            self.text = [shown.whoRead ?? shown.author, shown.level ?? "as written"].compactMap { $0 }.joined(separator: " · ")
        }
    }
}
