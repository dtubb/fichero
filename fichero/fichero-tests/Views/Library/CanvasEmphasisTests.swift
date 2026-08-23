//
//  CanvasEmphasisTests.swift
//  FicheroTests
//
//  §18.2 B / §25.4 step 2 — "pick a person or place, matching cards glow, the
//  rest dim, nothing moves". Entity highlight and a search's score-weighted
//  heat map are the same question asked twice, so they are ONE channel; these
//  pin the three properties that keep it one:
//
//   1. the normalisation (scores → weights) is defined once and is relative to
//      the visible answer, not to an absolute 0…1;
//   2. empty means NEUTRAL, not "nothing matched" — the None-vs-empty ambiguity
//      that has bitten this codebase before;
//   3. emphasis emits no move / resize / updateContent op, so a highlight can
//      never become a re-layout.
//

import CoreGraphics
@testable import Fichero
import Foundation
import simd
import Testing

private func node(_ id: String) -> SpatialNode {
    SpatialNode(id: id, roomId: "room", nodeType: .source, label: id,
                positionX: 0, positionY: 0, positionZ: 0)
}

@Suite("CanvasEmphasis (§25.4 step 2)")
struct CanvasEmphasisTests {

    @Test("empty is NEUTRAL: every card at full strength, nothing dimmed")
    func emptyMeansNeutral() {
        let neutral = CanvasEmphasis.neutral
        #expect(!neutral.isActive)
        #expect(neutral.strength(for: "doc:anything") == 1)
        #expect(CanvasEmphasis(weights: [:]) == neutral)
        // Not "nothing matched" — a producer with no answer must leave the
        // board alone rather than dim all of it.
        #expect(CanvasEmphasis.scoreWeighted(scores: [:]) == neutral)
    }

    @Test("an active emphasis dims what it did not name")
    func nonMatchesDim() {
        let emphasis = CanvasEmphasis(weights: ["doc:a": 1])
        #expect(emphasis.isActive)
        #expect(emphasis.strength(for: "doc:a") == 1)
        #expect(emphasis.strength(for: "doc:b") == CanvasEmphasis.dimmedStrength)
        // Dim, never invisible: where the hits FALL is half the answer, so the
        // rest of the board has to stay readable.
        #expect(CanvasEmphasis.dimmedStrength > 0)
        #expect(CanvasEmphasis.dimmedStrength < CanvasEmphasis.weakestMatchStrength)
    }

    @Test("every match outranks every non-match, however weak")
    func matchesAlwaysBeatTheGround() {
        let emphasis = CanvasEmphasis(weights: ["doc:strong": 1, "doc:weak": 0])
        #expect(emphasis.strength(for: "doc:weak") == CanvasEmphasis.weakestMatchStrength)
        #expect(emphasis.strength(for: "doc:weak") > emphasis.strength(for: "doc:absent"))
        #expect(emphasis.strength(for: "doc:strong") > emphasis.strength(for: "doc:weak"))
    }

    @Test("weights are clamped, and nonsense is dropped rather than rendered")
    func weightsAreSanitised() {
        let emphasis = CanvasEmphasis(weights: [
            "doc:over": 4, "doc:under": -2, "doc:nan": Double.nan, "doc:inf": Double.infinity, "doc:ok": 0.5,
        ])
        #expect(emphasis.strength(for: "doc:over") == 1)
        #expect(emphasis.strength(for: "doc:under") == CanvasEmphasis.weakestMatchStrength)
        // A non-finite weight is not a match at 0 — it is not an answer at all.
        #expect(emphasis.strength(for: "doc:nan") == CanvasEmphasis.dimmedStrength)
        #expect(emphasis.strength(for: "doc:inf") == CanvasEmphasis.dimmedStrength)
        #expect(emphasis.strength(for: "doc:ok") > CanvasEmphasis.weakestMatchStrength)
    }

    // MARK: Normalisation

    @Test("scores normalise across the VISIBLE range, not an absolute 0…1")
    func scoresNormaliseAcrossTheAnswer() {
        // SearchStore's floor is 0.55, so a tight query returns a narrow band of
        // high scores. Against an absolute scale every one of them would dim
        // together; against each other, the ranking is visible.
        let emphasis = CanvasEmphasis.scoreWeighted(
            scores: ["doc:a": 0.58, "doc:b": 0.62, "doc:c": 0.90]
        )
        #expect(emphasis.strength(for: "doc:c") == 1)
        #expect(emphasis.strength(for: "doc:a") == CanvasEmphasis.weakestMatchStrength)
        #expect(emphasis.strength(for: "doc:b") > emphasis.strength(for: "doc:a"))
        #expect(emphasis.strength(for: "doc:b") < emphasis.strength(for: "doc:c"))
    }

    @Test("a flat distribution is all-full, not all-zero")
    func flatScoresAreAllStrong() {
        // Identical scores carry no ranking. Rendering them as a uniform dim
        // would be inventing a distinction, in the direction that looks
        // confident — so they are all at full strength instead.
        let flat = CanvasEmphasis.scoreWeighted(scores: ["doc:a": 0.7, "doc:b": 0.7, "doc:c": 0.7])
        #expect(flat.isActive)
        for id in ["doc:a", "doc:b", "doc:c"] {
            #expect(flat.strength(for: id) == 1)
        }
        // Still an ANSWER, so everything it did not name is dimmed.
        #expect(flat.strength(for: "doc:elsewhere") == CanvasEmphasis.dimmedStrength)
    }

    @Test("a single hit is full strength, not a division by zero")
    func singleHit() {
        let one = CanvasEmphasis.scoreWeighted(scores: ["doc:only": 0.61])
        #expect(one.strength(for: "doc:only") == 1)
        #expect(one.strength(for: "doc:other") == CanvasEmphasis.dimmedStrength)
    }

    @Test("negative and non-finite scores cannot poison the scale")
    func degenerateScores() {
        // A non-finite score is dropped before the range is measured — one NaN
        // must not flatten every real score to the bottom of the scale.
        let mixed = CanvasEmphasis.scoreWeighted(
            scores: ["doc:a": 0.6, "doc:b": 0.9, "doc:bad": Double.nan, "doc:worse": Double.infinity]
        )
        #expect(mixed.strength(for: "doc:b") == 1)
        #expect(mixed.strength(for: "doc:a") == CanvasEmphasis.weakestMatchStrength)
        #expect(mixed.strength(for: "doc:bad") == CanvasEmphasis.dimmedStrength)

        // Negative scores still rank against each other rather than vanishing.
        let negative = CanvasEmphasis.scoreWeighted(scores: ["doc:a": -3, "doc:b": -1])
        #expect(negative.strength(for: "doc:b") == 1)
        #expect(negative.strength(for: "doc:a") == CanvasEmphasis.weakestMatchStrength)

        #expect(CanvasEmphasis.scoreWeighted(scores: ["doc:a": Double.nan]) == .neutral)
    }
}

// MARK: - Nothing moves

@Suite("Emphasis is diffed like selection, and moves nothing (R10)")
struct CanvasEmphasisDiffTests {

    private func state(_ ids: [String], emphasis: CanvasEmphasis = .neutral) -> CanvasSceneState {
        var state = CanvasSceneState.resolve(
            nodes: ids.map(node), connections: [], links: [], layoutRows: [], items: [],
            defaultPlacement: .grid(columns: 3)
        )
        state.emphasis = emphasis
        return state
    }

    @Test("a change in emphasis emits exactly one op, and it is setEmphasis")
    func emphasisEmitsOneOp() {
        let before = state(["a", "b", "c"])
        let after = state(["a", "b", "c"], emphasis: CanvasEmphasis(weights: ["a": 1]))
        let ops = CanvasSceneDiff.compute(from: before, to: after)
        #expect(ops == [.setEmphasis(CanvasEmphasis(weights: ["a": 1]))])
    }

    @Test("emphasis NEVER produces a move, resize or content op")
    func emphasisMovesNothing() {
        // The guarantee, as a test rather than a promise: a highlight that
        // re-laid the board out would be the opposite of what it is for — you
        // look at a heat map to see where things ALREADY are.
        let before = state(["a", "b", "c"], emphasis: CanvasEmphasis(weights: ["a": 1]))
        let after = state(["a", "b", "c"], emphasis: CanvasEmphasis(weights: ["b": 0.2, "c": 1]))
        let ops = CanvasSceneDiff.compute(from: before, to: after)
        for op in ops {
            switch op {
            case .move, .resize, .updateContent, .insert, .remove:
                Issue.record("emphasis produced a layout op: \(op)")
            // Not layout ops. `.setTint` is a sibling re-encode channel: it is
            // not what this test forbids, and `ops.count == 1` below is what
            // catches it firing when nothing asked it to.
            case .setEmphasis, .setSelection, .setEdges, .setTint:
                continue
            }
        }
        #expect(ops.count == 1)
        // And the positions really are identical on both sides.
        #expect(before.placeables.map(\.position) == after.placeables.map(\.position))
    }

    @Test("clearing a search returns to neutral in one op")
    func clearingEmitsNeutral() {
        let searching = state(["a", "b"], emphasis: CanvasEmphasis(weights: ["a": 1]))
        let cleared = state(["a", "b"])
        #expect(CanvasSceneDiff.compute(from: searching, to: cleared) == [.setEmphasis(.neutral)])
    }

    @Test("no emphasis change, no op — a re-render is not a re-highlight")
    func identicalEmphasisIsSilent() {
        let emphasis = CanvasEmphasis(weights: ["a": 0.5])
        #expect(CanvasSceneDiff.compute(from: state(["a", "b"], emphasis: emphasis),
                                        to: state(["a", "b"], emphasis: emphasis)).isEmpty)
    }

    @Test("selection and emphasis are independent channels")
    func selectionAndEmphasisDoNotInterfere() {
        var selected = state(["a", "b"])
        selected.selection = ["a"]
        var both = state(["a", "b"], emphasis: CanvasEmphasis(weights: ["b": 1]))
        both.selection = ["a"]
        #expect(CanvasSceneDiff.compute(from: selected, to: both)
                    == [.setEmphasis(CanvasEmphasis(weights: ["b": 1]))])
    }

    @Test("a fresh scene starts neutral, so nothing dims before a question is asked")
    func defaultStateIsNeutral() {
        #expect(CanvasSceneState.empty.emphasis == .neutral)
        #expect(state(["a"]).emphasis == .neutral)
    }
}

// MARK: - Wiring

/// What the pure layers cannot see: that emphasis reaches BOTH renderers
/// through the one channel, that it is painted without rebuilding a card, and
/// that the search producer normalises through `CanvasEmphasis` instead of
/// inventing a second scale.
struct CanvasEmphasisWiringGuardTests {
    private func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    /// Each renderer is a FILE SET, not a file: the 2026-08-22 split moved op
    /// application into +Ops.swift. A guard that keeps reading only the main
    /// file after a split still PASSES — on code it no longer contains — which
    /// is the failure mode this suite has already been bitten by once tonight.
    private let renderers = [
        ["Views/Library/ViewModes/Canvas/2D/CanvasOrtho2DRenderer.swift",
         "Views/Library/ViewModes/Canvas/2D/CanvasOrtho2DRenderer+Ops.swift"],
        ["Views/Library/ViewModes/Canvas/3D/CanvasScene3DRenderer.swift",
         "Views/Library/ViewModes/Canvas/3D/CanvasScene3DRenderer+Ops.swift"],
    ]

    private func combined(_ paths: [String]) throws -> String {
        try paths.map { try appSource($0) }.joined(separator: "\n")
    }

    @Test("both renderers handle setEmphasis through the shared painter")
    func bothRenderersPaintEmphasis() throws {
        for paths in renderers {
            let source = try combined(paths)
            #expect(source.contains("case .setEmphasis(let newEmphasis):"), "\(paths) ignores emphasis")
            #expect(source.contains("CanvasEmphasisPainter.apply("), "\(paths) drew its own highlight")
        }
    }

    /// One `case` body out of an `applyOne` switch.
    ///
    /// It ends at the next case OR at the switch's own closing brace, whichever
    /// comes first. Slicing only on the next case was wrong in the way that
    /// matters: `.setEmphasis` is the LAST case, so the window ran past the
    /// switch and swallowed the methods below it — including `reskinCard`,
    /// which rebuilds a card quite legitimately. The guard then failed on code
    /// it was never about.
    private func caseBody(_ source: String, forCase marker: String) throws -> String {
        let tail = try #require(source.components(separatedBy: marker).last)
        let end = ["\n        case ", "\n        }"]
            .compactMap { tail.range(of: $0)?.lowerBound }
            .min() ?? tail.endIndex
        return String(tail[..<end])
    }

    @Test("emphasis never rebuilds a card — the #4409 rule, restated")
    func emphasisNeverReskins() throws {
        for paths in renderers {
            let handler = try caseBody(try combined(paths), forCase: "case .setEmphasis")
            #expect(!handler.isEmpty)
            #expect(!handler.contains("reskinCard"), "\(paths) rebuilds cards to highlight them")
            #expect(!handler.contains("makeCard"), "\(paths) rebuilds cards to highlight them")
            // What it does instead, so the slice can't pass by being empty.
            #expect(handler.contains("CanvasEmphasisPainter.apply("))
        }
    }

    @Test("the slice really is one case body — the selection case is excluded")
    func caseSliceIsBounded() throws {
        // A guard whose scan window is wrong reports on code it was never
        // about, which is how this test suite lied once already.
        for paths in renderers {
            let handler = try caseBody(try combined(paths), forCase: "case .setEmphasis")
            #expect(!handler.contains("case .setSelection"))
            #expect(!handler.contains("func "))
        }
    }

    @Test("a rebuilt card keeps its emphasis")
    func reskinRepaintsEmphasis() throws {
        // A rebuilt entity carries none of the old one's components, so a card
        // whose thumbnail lands mid-search would come back bright among dimmed
        // neighbours. 2D's reskin lives in its +Thumbnails file (the main one
        // is at its file_length ceiling); 3D's is still in the renderer.
        let reskinHomes = [
            "Views/Library/ViewModes/Canvas/2D/CanvasOrtho2DRenderer+Thumbnails.swift",
            "Views/Library/ViewModes/Canvas/3D/CanvasScene3DRenderer.swift",
        ]
        for path in reskinHomes {
            let source = try appSource(path)
            let reskin = try #require(source.components(separatedBy: "func reskinCard").last)
                .components(separatedBy: "\n    ").prefix(12).joined(separator: "\n    ")
            #expect(reskin.contains("CanvasEmphasisPainter.apply("), "\(path) loses emphasis on reskin")
        }
    }

    @Test("the search producer normalises through CanvasEmphasis, once")
    func searchProducerUsesTheSharedNormalisation() throws {
        let host = try appSource("Views/Library/LibraryView+CanvasModes.swift")
        #expect(host.contains("CanvasEmphasis.scoreWeighted("))
        // Document ids cross into placeable ids at the producer — the channel
        // itself never learns about documents.
        #expect(host.contains("SpatialLibraryProjector.nodeId(forDocument:"))
        // Both engine canvases receive it; the legacy ones deliberately do not.
        #expect(host.components(separatedBy: "emphasis: canvasSearchEmphasis").count - 1 == 2)
    }
}
