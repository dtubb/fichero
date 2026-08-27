@testable import Fichero
import Foundation
import Testing

/// #4394: a claim badge read `0.70`.
///
/// The value comes from `workflows/tools/extractors.py`, where it is a number
/// the LLM emitted alongside the claim — not a measurement of whether the claim
/// is true. Rendering it to two decimals asserts a precision that does not
/// exist, in the densest part of the inspector, next to facts that ARE
/// measured. And the badge was unlabelled: a bare decimal in a capsule could be
/// a score, a page, a version or a weight.
///
/// A band is the most the signal supports.
struct ConfidenceBandTests {

    // MARK: - No false precision

    /// The defect, stated directly: two values a user cannot meaningfully
    /// distinguish must not be rendered as if they could be.
    @Test("neighbouring values do not read as different")
    func neighbouringValuesDoNotReadAsDifferent() {
        #expect(ConfidenceBand.band(for: 0.70) == ConfidenceBand.band(for: 0.65))
        #expect(ConfidenceBand.band(for: 0.70).badgeText == ConfidenceBand.band(for: 0.65).badgeText)
    }

    /// Nothing anywhere renders a decimal — that is the whole point.
    @Test("no band ever renders a number")
    func noBandRendersANumber() {
        for band in ConfidenceBand.allCases {
            for text in [band.badgeText, band.label, band.short, band.help] {
                // `contains(".")` on a String resolves to the RegexComponent
                // overload, which is throwing — inside a non-throwing @Test the
                // macro expansion then fails to compile. Compare Characters so
                // the plain Sequence overload is chosen and no `try` is needed.
                #expect(!text.contains(Character(".")), Comment(rawValue: text))
                #expect(!text.contains(where: { $0.isNumber }), Comment(rawValue: text))
            }
        }
    }

    // MARK: - Always labelled

    /// "A lozenge reading `0.70` explains nothing." The badge must say what it
    /// measures without a hover.
    @Test("the badge names what it measures")
    func badgeNamesWhatItMeasures() {
        for band in ConfidenceBand.allCases {
            #expect(band.badgeText.hasPrefix("conf "), Comment(rawValue: band.badgeText))
            #expect(!band.badgeText.isEmpty)
        }
    }

    /// The tooltip carries the honesty about provenance: a user deciding
    /// whether to trust or delete a claim needs to know this is the model's own
    /// estimate, not a measurement.
    @Test("the tooltip says the number is the model's own estimate")
    func tooltipStatesProvenance() {
        for band in ConfidenceBand.allCases {
            #expect(band.help.contains("model"), Comment(rawValue: band.help))
            #expect(band.help.contains("not a measurement"), Comment(rawValue: band.help))
        }
    }

    // MARK: - Absent is not 0.5

    /// **The defect, stated as the test that catches it.**
    ///
    /// "No confidence was recorded" and "the model said 0.5" are different
    /// facts, and a historian deciding whether to trust or delete a claim
    /// would act differently on each. This fails the moment they collapse to
    /// the same rendering — which is exactly what `confidence ?? 0.5` does,
    /// and `?? 0.5` is the tidy-looking edit somebody will eventually make.
    @Test("an absent confidence does not render as a recorded 0.5")
    func absentDoesNotRenderAsARecordedHalf() {
        let absent = ConfidenceBand.recorded(nil)
        let half = ConfidenceBand.recorded(0.5)

        #expect(absent?.badgeText != half?.badgeText)
        #expect(absent?.label != half?.label)
        #expect(absent?.help != half?.help)
    }

    /// The chosen rendering for absence, named so a future change to it is a
    /// deliberate decision rather than a side effect: NOTHING. Not a
    /// placeholder, not a dash, not a midpoint. A badge shown for a value
    /// nobody produced cannot be told apart from one that was, and #4421's
    /// standing rule is that a half-working affordance is worse than an
    /// absent one.
    @Test("an absent confidence renders nothing at all")
    func absentRendersNothing() {
        #expect(ConfidenceBand.recorded(nil) == nil)
    }

    /// The other half: a value that IS there still bands, so "renders
    /// nothing" cannot be satisfied by rendering nothing for everything.
    @Test("a recorded confidence still bands")
    func recordedStillBands() {
        #expect(ConfidenceBand.recorded(0.5) == .medium)
        #expect(ConfidenceBand.recorded(0.0) == .low)
        #expect(ConfidenceBand.recorded(1.0) == .high)
    }

    /// A recorded 0.0 is a fact — the model scored it and scored it lowest.
    /// It must not be swallowed as if it were absent, which is the mirror of
    /// the reported bug and the failure a naive `if confidence > 0` check
    /// would introduce while looking like a fix.
    @Test("a recorded zero is not treated as absent")
    func recordedZeroIsNotAbsent() {
        #expect(ConfidenceBand.recorded(0.0) != nil)
        #expect(ConfidenceBand.recorded(0.0)?.badgeText != ConfidenceBand.recorded(nil)?.badgeText)
    }

    // MARK: - Absent is not zero when ranking either

    /// Sorting with `confidence ?? 0` is the same silent substitution wearing
    /// different clothes: it ranks a claim nobody scored exactly where it
    /// ranks a claim the model scored 0.0.
    @Test("unrecorded does not rank as a recorded zero")
    func unrecordedDoesNotRankAsZero() {
        #expect(ConfidenceBand.ordersBefore(0.0, nil) == true)
        #expect(ConfidenceBand.ordersBefore(nil, 0.0) == false)
    }

    /// Recorded values rank by value, strongest first — the existing
    /// behaviour, which the fix must not disturb.
    @Test("recorded values still rank strongest first")
    func recordedValuesRankStrongestFirst() {
        #expect(ConfidenceBand.ordersBefore(0.9, 0.5) == true)
        #expect(ConfidenceBand.ordersBefore(0.5, 0.9) == false)
    }

    /// `nil` means "no opinion, use your own tiebreak" — not "equal", and not
    /// "before". Two unrecorded claims fall through to the name ordering
    /// rather than landing in whatever order they arrived, which is what makes
    /// the list stable.
    @Test("ties defer to the caller instead of inventing an order")
    func tiesDeferToTheCaller() {
        #expect(ConfidenceBand.ordersBefore(nil, nil) == nil)
        #expect(ConfidenceBand.ordersBefore(0.7, 0.7) == nil)
    }

    /// The comparator has to be a strict weak ordering or `sorted(by:)` is
    /// free to misbehave. Asymmetry across every interesting pair — including
    /// the absent ones, which are the new cases — is the property that
    /// guarantees it.
    @Test("the ordering is asymmetric across every pair")
    func theOrderingIsAsymmetric() {
        let values: [Double?] = [nil, 0.0, 0.4, 0.5, 0.75, 1.0]
        for left in values {
            for right in values {
                let forward = ConfidenceBand.ordersBefore(left, right)
                let backward = ConfidenceBand.ordersBefore(right, left)
                let pair = Comment(rawValue: "\(String(describing: left)) vs \(String(describing: right))")
                if let forward, let backward {
                    #expect(forward != backward, pair)
                } else {
                    #expect(forward == nil && backward == nil, pair)
                }
            }
        }
    }

    // MARK: - Banding

    @Test("the bands cover the range in order")
    func bandsCoverTheRangeInOrder() {
        #expect(ConfidenceBand.band(for: 0.0) == .low)
        #expect(ConfidenceBand.band(for: 0.39) == .low)
        #expect(ConfidenceBand.band(for: 0.4) == .medium)
        #expect(ConfidenceBand.band(for: 0.5) == .medium)
        #expect(ConfidenceBand.band(for: 0.74) == .medium)
        #expect(ConfidenceBand.band(for: 0.75) == .high)
        #expect(ConfidenceBand.band(for: 1.0) == .high)
    }

    /// Banding is monotonic: a higher self-report can never band lower. A
    /// non-monotonic mapping would be worse than the decimal it replaced.
    @Test("a higher value never bands lower")
    func bandingIsMonotonic() {
        let order: [ConfidenceBand: Int] = [.low: 0, .medium: 1, .high: 2]
        var previous = 0
        for step in 0...100 {
            let rank = order[ConfidenceBand.band(for: Double(step) / 100)] ?? -1
            #expect(rank >= previous, Comment(rawValue: "\(step)"))
            previous = rank
        }
    }

    /// Out-of-range input is clamped rather than crashing or banding oddly —
    /// the engine clamps too, but the client cannot assume it was reached.
    @Test("out-of-range values are clamped, not rejected")
    func outOfRangeIsClamped() {
        #expect(ConfidenceBand.band(for: -5) == .low)
        #expect(ConfidenceBand.band(for: 42) == .high)
        #expect(ConfidenceBand.band(for: .infinity) == .high)
        #expect(ConfidenceBand.band(for: -.infinity) == .low)
    }

    /// Whatever arrives, something renders — a badge that vanishes on a
    /// malformed value looks like a missing field.
    @Test("every finite input produces a usable badge")
    func everyInputProducesABadge() {
        for value in stride(from: -1.0, through: 2.0, by: 0.05) {
            let band = ConfidenceBand.band(for: value)
            #expect(!band.badgeText.isEmpty, Comment(rawValue: "\(value)"))
            #expect(!band.help.isEmpty)
        }
    }

    // MARK: - Structural: every confidence surface bands

    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    private static func codeOnly(_ source: String) -> String {
        source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    /// The reported badge, plus the three siblings that rendered the same
    /// signal the same way. Fixing one and leaving three is how the class
    /// survives — the same lesson as #4416's twelve surfaces.
    @Test("every confidence surface renders a band, not a decimal")
    func everyConfidenceSurfaceBands() throws {
        for surface in Self.badgeSurfaces {
            let source = try Self.codeOnly(Self.appSource(surface))
            #expect(source.contains("ConfidenceBand."), Comment(rawValue: surface))
        }
    }

    /// The four surfaces that render a model-reported confidence.
    private static let badgeSurfaces = [
        "Views/Inspector/Knowledge/EntityKindRow+ClaimBlock.swift",
        "Views/Inspector/Source/Info/DocumentInspectorInfoTab+Citations.swift",
        "Views/Inspector/Knowledge/Citations/CitationListView.swift",
        "Views/Inspector/Knowledge/Citations/CitationDetailView.swift"
    ]

    /// Each of them must route absence through `recorded(_:)` rather than
    /// through its own `if let`. Four private `if let`s are four places the
    /// distinction can be lost independently, and three of them would still be
    /// green when the fourth broke — the shape that let this defect exist in
    /// four surfaces at once in the first place.
    @Test("every confidence surface routes absence through one seam")
    func everySurfaceRoutesAbsenceThroughOneSeam() throws {
        for surface in Self.badgeSurfaces {
            let source = try Self.codeOnly(Self.appSource(surface))
            #expect(source.contains("ConfidenceBand.recorded("), Comment(rawValue: surface))
        }
    }

    /// A real directory sweep, not a named-file list: nowhere in the knowledge
    /// surfaces may a confidence be defaulted with `??`.
    ///
    /// `confidence ?? 0.5` and `confidence ?? 0` are the two shapes this issue
    /// is about — one substitutes a rendering, the other substitutes a rank —
    /// and both look tidy enough to survive review. A named-file list would
    /// not see a fifth surface added next month; this does.
    ///
    /// Scoped to the KG / citation surfaces on purpose. A user's OWN
    /// interpretation confidence (Views/Inspector/Notes) is a value a person
    /// typed on a slider, not a model's self-report, and seeding an editor
    /// with a default the user can see and change is not the same act as
    /// printing an invented number as if it were recorded.
    @Test("no knowledge surface defaults a confidence with ??")
    func noKnowledgeSurfaceDefaultsAConfidence() throws {
        let roots = ["Views/Inspector/Knowledge", "Views/Inspector/Source"]
        var scanned = 0
        var offenders: [String] = []

        for root in roots {
            let directory = try AppSource.root().appendingPathComponent(root)
            let files = FileManager.default.enumerator(at: directory, includingPropertiesForKeys: nil)?
                .compactMap { $0 as? URL }
                .filter { $0.pathExtension == "swift" } ?? []
            for file in files {
                scanned += 1
                let source = Self.codeOnly(try String(contentsOf: file, encoding: .utf8))
                if source.range(of: #"[Cc]onfidence\s*\?\?"#, options: .regularExpression) != nil {
                    offenders.append(file.lastPathComponent)
                }
            }
        }

        #expect(scanned > 0, "the sweep must actually read files")
        let message = "a confidence is defaulted with ?? in: \(offenders.joined(separator: ", "))"
        #expect(offenders.isEmpty, Comment(rawValue: message))
    }

    /// #4447: the four named surfaces above prove EACH ONE bands, but a fifth
    /// surface added later that formats a raw confidence with `%.2f` would
    /// sail through untested — the invariant is "the app never renders a raw
    /// confidence decimal", not "these four files don't". So this half is a
    /// real directory sweep, not a named-file list: nowhere under `Views/`
    /// does any file format `"%.2f", confidence` (verified zero occurrences
    /// app-wide before landing, so this cannot be a false-red on day one).
    @Test("nowhere in the app does a confidence render as a raw decimal")
    func noSurfaceAnywhereFormatsARawConfidence() throws {
        let root = try AppSource.root().appendingPathComponent("Views")

        let files = FileManager.default.enumerator(at: root, includingPropertiesForKeys: nil)?
            .compactMap { $0 as? URL }
            .filter { $0.pathExtension == "swift" } ?? []
        #expect(!files.isEmpty, "the sweep must actually read files")

        var offenders: [String] = []
        for file in files {
            let source = try String(contentsOf: file, encoding: .utf8)
            if source.contains("\"%.2f\", confidence") {
                offenders.append(file.lastPathComponent)
            }
        }
        let message = "raw confidence formatting in: \(offenders.joined(separator: ", "))"
        #expect(offenders.isEmpty, Comment(rawValue: message))
    }

    /// Similarity scores are deliberately NOT banded: a cosine distance is a
    /// computed measurement, not a model's opinion of itself. Banding it would
    /// destroy real precision to fix a different problem.
    @Test("similarity scores keep their precision")
    func similarityKeepsItsPrecision() throws {
        let source = try Self.appSource(
            "Views/Inspector/Source/Info/DocumentInspectorInfoTab+RelatedClaims.swift")
        #expect(source.contains("similarityScore"))
        #expect(source.contains("%.2f"), "a measured score may show its value")
    }
}
