/// The Inspector's Text section (ruled 2026-09-27, `build-notes-inspector.md` 5.1): every live
/// reading of the inspected segment, which one counts for each kind, and WHY.
///
/// The why is never optional here. The contract's own words for `CountingBasis`: a caller that reads
/// only which reading counts and drops the basis turns "a machine guessed this, nobody has checked
/// it" into "this is the text". So the answer and its reason travel together.
struct InspectorText: Equatable {
    struct Reading: Equatable, Identifiable {
        let id: String
        let kind: String
        let content: String
        /// Who made it, as a kind: a person, a workflow, an import.
        let maker: String
        /// Which account, when the engine knows (`source.reading.author-and-guideline`).
        let author: String?
        let guideline: String?
        /// A written / read pair (sic and corr, abbr and expan): same `pairId`, each with its role.
        let pairId: String?
        let pairRole: String?
        /// The reading this one corrects, when it is a correction (`source.reading.corrections-are-new`).
        var correctsId: String?
        /// The normalisation level it was made at (diplomatic, normalised, ...), as recorded.
        var level: String?
        /// A machine's own confidence, 0-1 -- never shown for a person's reading, which has none.
        var machineConfidence: Double?
        /// The rendition it was read from, when not the page's own image.
        var readFromRenditionId: String?
    }

    enum Why: Equatable {
        case chosen, newestHuman, newestMachineUnchosen, noneCounts
        /// A basis this build does not know. Shown as itself, never quietly read as one we do.
        case unknown(String)

        init(basis: String?) {
            switch basis {
            case "chosen": self = .chosen
            case "newest-human": self = .newestHuman
            case "newest-machine-unchosen": self = .newestMachineUnchosen
            case "none", nil: self = .noneCounts
            case let other?: self = .unknown(other)
            }
        }

        /// What the section says beside the counting reading.
        var label: String {
            switch self {
            case .chosen: "Chosen by a person"
            case .newestHuman: "Newest reading by a person"
            case .newestMachineUnchosen: "Machine reading, not yet checked"
            case .noneCounts: "No reading counts yet"
            case .unknown(let basis): "Counts (\(basis))"
            }
        }
    }

    struct Counting: Equatable {
        let readingId: String?
        let why: Why
    }

    /// Live readings in the engine's order; a retracted one is history, not a reading, and is left out.
    let readings: [Reading]
    /// Per kind: which reading counts and why.
    let counting: [String: Counting]

    init(readings: [Reading], retracted: Set<String> = [], counting: [String: Counting]) {
        self.readings = readings.filter { !retracted.contains($0.id) }
        self.counting = counting
    }

    /// The kinds present, in the order first seen.
    var kinds: [String] {
        var seen: [String] = []
        for reading in readings where !seen.contains(reading.kind) { seen.append(reading.kind) }
        return seen
    }

    func readings(ofKind kind: String) -> [Reading] { readings.filter { $0.kind == kind } }

    func counts(_ reading: Reading) -> Bool { counting[reading.kind]?.readingId == reading.id }

    /// The other half of a written / read pair, shown beside it as a pair.
    func partner(of reading: Reading) -> Reading? {
        guard let pairId = reading.pairId else { return nil }
        return readings.first { $0.pairId == pairId && $0.id != reading.id }
    }
}
