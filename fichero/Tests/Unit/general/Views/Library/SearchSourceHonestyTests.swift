@testable import Fichero
import Foundation
import Testing

/// The chips must name the leg that actually ran (Daniel, live 2026-09-03:
/// rows were badged "graph" in a library with essentially no graph, while the
/// graph tier was switched off).
///
/// The engine was honest: `match_sources` carries "kg" only when the opt-in
/// `hybrid_graph` fusion leg ran. The CLIENT invented the label. Every row
/// reached by the entity or claim leg — semantic searches over the entity and
/// claim tables, which the shell requests on EVERY search via
/// `include: [.content, .entities, .claims, .artifacts]` — was tagged `.kg`
/// and drew the word "graph". A chip that claims a capability the library was
/// never given is worse than no chip.
@MainActor
struct SearchSourceHonestyTests {

    // MARK: - One word per leg, and the words are different

    @Test("the entity and claim legs are their own sources, not the graph")
    func entityAndClaimAreDistinctFromTheGraph() {
        #expect(SearchMatchSource.entity != SearchMatchSource.kg)
        #expect(SearchMatchSource.claim != SearchMatchSource.kg)
        #expect(SearchMatchSource.entity.chipLabel == "entity")
        #expect(SearchMatchSource.claim.chipLabel == "claim")
    }

    /// "graph" stays reserved for the one leg entitled to it.
    @Test("only the knowledge-graph leg is labelled graph")
    func onlyTheKGLegSaysGraph() {
        let graphLabelled = SearchMatchSource.allCases
            .filter { $0.chipLabel == "graph" }
        #expect(graphLabelled == [.kg])
    }

    /// Semantic still earns no chip: it is what the % badge already says, and
    /// a chip on every row is a chip that says nothing.
    @Test("the semantic leg still draws no chip")
    func semanticDrawsNoChip() {
        #expect(SearchMatchSource.semantic.chipLabel == nil)
        #expect(SearchMatchSource.fulltext.chipLabel == "exact")
    }

    /// Each chip explains itself, and no two legs share an explanation — the
    /// help text is what the chip means, so a duplicate is a lie about one
    /// of them.
    @Test("every leg explains itself, and no two explanations collide")
    func chipHelpIsDistinctPerLeg() {
        let helps = SearchMatchSource.allCases.map(\.chipHelp)
        #expect(Set(helps).count == helps.count)
        #expect(!SearchMatchSource.entity.chipHelp.contains("graph"))
        #expect(!SearchMatchSource.claim.chipHelp.contains("graph"))
    }

    // MARK: - Parsing what the engine actually sends

    /// The engine's own vocabulary still round-trips, including the new
    /// names, and anything unknown is dropped rather than given a chip.
    @Test("the engine's leg names parse, and unknown names are dropped")
    func parseKeepsKnownLegsAndDropsTheRest() {
        #expect(SearchMatchSource.parse(["kg"]) == [.kg])
        #expect(SearchMatchSource.parse(["fulltext", "semantic"]) == [.fulltext, .semantic])
        #expect(SearchMatchSource.parse(["entity", "claim"]) == [.entity, .claim])
        #expect(SearchMatchSource.parse(["content-scan", "wormhole"]).isEmpty)
    }

    // MARK: - The shell tags the legs it synthesises honestly

    /// `ContentView.rowHits` folds entity- and claim-leg hits in as rows the
    /// engine's `match_sources` never described, so it labels them itself.
    /// It labelled both `.kg`; it must now name them for what they are.
    @Test("the shell tags entity and claim leg rows as entity and claim")
    func shellTagsSynthesisedRowsHonestly() throws {
        let source = try String(
            contentsOf: AppSource.root()
                .appendingPathComponent("Views/Shell/ContentView/ContentView+SearchResults.swift"),
            encoding: .utf8
        )
        #expect(source.contains("matchSources: [.entity]"))
        #expect(source.contains("matchSources: [.claim]"))
        #expect(!source.contains("matchSources: [.kg]"))
    }
}
