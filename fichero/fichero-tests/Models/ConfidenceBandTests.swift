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
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
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
        let surfaces = [
            "Views/Inspector/Knowledge/EntityKindRow+ClaimBlock.swift",
            "Views/Inspector/Source/Info/DocumentInspectorInfoTab+Citations.swift",
            "Views/Inspector/Knowledge/Citations/CitationListView.swift",
            "Views/Inspector/Knowledge/Citations/CitationDetailView.swift"
        ]
        for surface in surfaces {
            let source = try Self.codeOnly(Self.appSource(surface))
            #expect(source.contains("ConfidenceBand.band(for:"), Comment(rawValue: surface))
            #expect(
                !source.contains("\"%.2f\", confidence"),
                Comment(rawValue: "\(surface) still formats a raw confidence"))
        }
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
