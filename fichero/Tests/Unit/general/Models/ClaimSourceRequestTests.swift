@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// #4393 part 2: a claim was the only thing in the inspector you could not get
/// back to the page from.
///
/// Not because the addressing was missing. `ClaimSourceNavigationRequest`
/// already carries `charStart`, `charEnd`, `bbox`, `pageIndex` and `pageLabel`,
/// and already had four producers — annotations, artifacts, the source outline
/// and the KG web pane. The claims list was never one of them. The missing end
/// here is the producer, not the consumer.
///
/// The rule these tests exist for: **never approximate a location.** A claim
/// with no recorded span opens its page and says so. A confidently wrong
/// highlight over a manuscript asserts a word appears somewhere it does not,
/// and the reader has no way to discover it is wrong.
struct ClaimSourceRequestTests {

    private func claim(
        id: String? = "claim-1",
        documentId: String? = "doc-1",
        charStart: Int? = 120,
        charEnd: Int? = 180,
        bbox: [Double]? = nil,
        pageLabel: String? = "4"
    ) -> Components.Schemas.KnowledgeClaim {
        Components.Schemas.KnowledgeClaim(
            id: id,
            text: "compareció ante el notario",
            sourceDocumentId: documentId,
            sourcePageLabel: pageLabel,
            sourceCharStart: charStart,
            sourceCharEnd: charEnd,
            sourceBbox: bbox
        )
    }

    // MARK: - Span level, which is the whole point

    @Test("a claim with a recorded span navigates at span level")
    func spanClaimNavigatesAtSpanLevel() throws {
        #expect(ClaimSourceRequest.precision(for: claim()) == .span)

        let request = try #require(ClaimSourceRequest.request(for: claim()))
        #expect(request.documentId == "doc-1")
        #expect(request.charStart == 120)
        #expect(request.charEnd == 180)
        #expect(request.destination == .reader)
    }

    @Test("a claim with only a region navigates at region level")
    func regionClaimNavigatesAtRegionLevel() throws {
        let regional = claim(charStart: nil, charEnd: nil, bbox: [0.1, 0.2, 0.3, 0.4])
        #expect(ClaimSourceRequest.precision(for: regional) == .region)

        let request = try #require(ClaimSourceRequest.request(for: regional))
        #expect(request.bbox == [0.1, 0.2, 0.3, 0.4])
        #expect(request.charStart == nil)
    }

    // MARK: - Never approximate

    /// The rule, stated directly: no span, no highlight — but still navigate.
    @Test("a claim with no span opens its page without drawing a highlight")
    func pageOnlyClaimDrawsNoHighlight() throws {
        let vague = claim(charStart: nil, charEnd: nil)
        #expect(ClaimSourceRequest.precision(for: vague) == .pageOnly)
        #expect(!ClaimSourceRequest.precision(for: vague).drawsHighlight)

        let request = try #require(ClaimSourceRequest.request(for: vague))
        #expect(request.pageLabel == "4", "it still goes to the page")
        #expect(request.charStart == nil)
        #expect(request.charEnd == nil)
        #expect(request.bbox == nil)
    }

    /// The property that makes a wrong highlight impossible rather than
    /// unlikely: no combination of inputs yields highlight coordinates unless
    /// the precision vouched for them.
    @Test("no request ever carries coordinates its precision did not vouch for")
    func coordinatesOnlyAtVouchedPrecision() {
        let starts: [Int?] = [nil, 0, 120]
        let ends: [Int?] = [nil, 0, 120, 180]
        let boxes: [[Double]?] = [nil, [], [0.1, 0.2], [0.1, 0.2, 0.3, 0.4]]

        for start in starts {
            for end in ends {
                for box in boxes {
                    let candidate = claim(charStart: start, charEnd: end, bbox: box)
                    let precision = ClaimSourceRequest.precision(for: candidate)
                    guard let request = ClaimSourceRequest.request(for: candidate) else { continue }
                    let label = Comment(
                        rawValue: "\(String(describing: start))/"
                            + "\(String(describing: end))/\(String(describing: box))")
                    if precision != .span {
                        #expect(request.charStart == nil, label)
                        #expect(request.charEnd == nil, label)
                    }
                    if precision != .region {
                        #expect(request.bbox == nil, label)
                    }
                }
            }
        }
    }

    /// A zero-length span addresses no text. Highlighting it would put a caret
    /// at an arbitrary place and claim it was the source.
    @Test("an empty span is treated as no span")
    func emptySpanIsNoSpan() {
        #expect(ClaimSourceRequest.precision(for: claim(charStart: 50, charEnd: 50)) == .pageOnly)
        #expect(ClaimSourceRequest.precision(for: claim(charStart: 90, charEnd: 20)) == .pageOnly)
    }

    /// A malformed bbox is not a region. Four numbers or nothing.
    @Test("a malformed bbox is not a region")
    func malformedBboxIsNotARegion() {
        for box in [[], [0.1], [0.1, 0.2], [0.1, 0.2, 0.3]] as [[Double]] {
            let candidate = claim(charStart: nil, charEnd: nil, bbox: box)
            #expect(ClaimSourceRequest.precision(for: candidate) == .pageOnly,
                    Comment(rawValue: "\(box.count) components"))
        }
    }

    // MARK: - Nowhere honest to go

    @Test("a claim with no document produces no request at all")
    func noDocumentProducesNoRequest() {
        #expect(ClaimSourceRequest.precision(for: claim(documentId: nil)) == .unknown)
        #expect(ClaimSourceRequest.request(for: claim(documentId: nil)) == nil)
        #expect(ClaimSourceRequest.request(for: claim(documentId: "   ")) == nil)
    }

    /// Every imprecise outcome explains itself; a silent navigation to the
    /// wrong-looking place reads as a bug.
    @Test("every imprecise precision carries a caveat, and exact ones do not")
    func imprecisionIsExplained() {
        #expect(ClaimSourceRequest.Precision.span.caveat == nil)
        #expect(ClaimSourceRequest.Precision.region.caveat == nil)
        #expect(ClaimSourceRequest.Precision.pageOnly.caveat?.isEmpty == false)
        #expect(ClaimSourceRequest.Precision.unknown.caveat?.isEmpty == false)
    }

    // MARK: - One cursor, not a third scheme

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

    /// The constraint that matters more than the feature: claims write to the
    /// EXISTING cursor, the same one the source outline uses. A third
    /// addressing scheme is the failure this codebase keeps producing.
    @Test("claims drive the shared cursor, not a new one")
    func claimsDriveTheSharedCursor() throws {
        let digest = try Self.codeOnly(
            Self.appSource("Views/Inspector/Knowledge/EntityDigestView.swift"))

        #expect(digest.contains("ClaimSourceRequest.request(for: claim)"))
        #expect(digest.contains("claimSourceNavigationState?.request(request)"))
        // The same seam the outline writes to — not a parallel one.
        let outline = try Self.appSource("Views/Inspector/Source/SourceOutlineView.swift")
        #expect(outline.contains("claimSourceNavigationState?.request(request)"))
    }

    /// #4393 also asked for the bracketed internal filename to go. It was built
    /// from the STORAGE name and looked up only in `currentDocuments`, so it
    /// printed an internal identifier and vanished depending on what else was
    /// loaded — a citation that changes with unrelated state.
    @Test("the biography no longer appends an internal filename")
    func biographyDropsTheInternalCitation() throws {
        let digest = try Self.codeOnly(
            Self.appSource("Views/Inspector/Knowledge/EntityDigestView.swift"))
        #expect(!digest.contains("let citation"))
        #expect(!digest.contains("currentDocuments.first("))
    }
}
