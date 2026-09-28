import Foundation

/// The Inspector's Hands section (#5161; `build-notes-inspector.md` 5.4). Who wrote the INK and who
/// made the RECORD are kept apart (`source.hand.not-provenance`): each attribution names the hand, how
/// sure the judgement is, and who judged it -- a person, or the imported file. Rival attributions are
/// all shown, never merged (`source.hand.attributed`).
enum InspectorHands {
    struct Hand: Equatable, Identifiable {
        let id: String
        let label: String
        let scribe: String?
        let date: String?
        let style: String?
    }

    struct Attribution: Equatable, Identifiable {
        let id: String
        let handId: String
        /// Scholarly certainty, 0-1, or nil when the judge did not say.
        let certainty: Double?
        let judgedBy: String?
        /// "file: <name>" when an import's file said so; nil for a judgement made here.
        let fromFile: String?
    }

    struct Row: Equatable, Identifiable {
        let attributionId: String
        /// Who wrote the ink: "hand B" (with the scribe or style when known).
        let ink: String
        /// Who made the record and how sure: "judged by owner · sure 80%", "from the file 0065.xml".
        let record: String
        var id: String { attributionId }
    }

    static func rows(_ attributions: [Attribution], hands: [Hand]) -> [Row] {
        let byId = Dictionary(hands.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        return attributions.map { attribution in
            let hand = byId[attribution.handId]
            var ink = hand?.label ?? "an unlisted hand"
            if let detail = hand.flatMap({ $0.scribe ?? $0.style }) { ink += " (\(detail))" }
            var record: [String] = []
            if let file = attribution.fromFile {
                record.append(file.hasPrefix("file: ") ? "from the file \(file.dropFirst("file: ".count))" : file)
            } else if let judge = attribution.judgedBy {
                record.append("judged by \(judge)")
            }
            if let certainty = attribution.certainty {
                record.append("sure \(Int((certainty * 100).rounded()))%")
            }
            return Row(attributionId: attribution.id, ink: ink, record: record.joined(separator: " · "))
        }
    }
}
