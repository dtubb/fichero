//
//  ShellPrimarySelectionTests.swift
//  FicheroTests
//
//  Pins the 2026-08-09 selection-identity fix: the shell's browserSelection
//  handler drew `Set.first` THREE times (entity focus, preview promotion,
//  stale-fetch guard) — hash order, so each draw could name a DIFFERENT
//  element of the same multi-selection, and actions could target a row the
//  user never considered primary. One helper now answers in DOCUMENT ORDER
//  (what the user sees), with a stable lexical fallback for unloaded ids.
//

import Foundation
import Testing
@testable import Fichero

struct ShellPrimarySelectionTests {

    private func doc(_ id: String) -> Document {
        Document(id: id, docType: .file, name: id)
    }

    @Test("primary follows the visible document order, not set hash order")
    func documentOrderWins() {
        let docs = [doc("c"), doc("a"), doc("b")]
        #expect(shellPrimarySelectionId(in: ["a", "b"], orderedBy: docs) == "a")
        #expect(shellPrimarySelectionId(in: ["b", "c"], orderedBy: docs) == "c")
    }

    @Test("ids not in the loaded list fall back to the stable lexical minimum")
    func unloadedFallsBackStably() {
        #expect(shellPrimarySelectionId(in: ["z-late", "m-mid"], orderedBy: []) == "m-mid")
        // Deterministic across calls — the property Set.first lacks.
        for _ in 0..<10 {
            #expect(shellPrimarySelectionId(in: ["z", "y", "x"], orderedBy: []) == "x")
        }
    }

    @Test("empty selection has no primary")
    func emptyIsNil() {
        #expect(shellPrimarySelectionId(in: [], orderedBy: [doc("a")]) == nil)
    }

    @Test("a partially-loaded selection still prefers the visible member")
    func partiallyLoadedPrefersVisible() {
        // "z-visible" is on screen; "a-unloaded" would win the lexical
        // fallback — visibility must win over lexical order.
        #expect(
            shellPrimarySelectionId(in: ["a-unloaded", "z-visible"], orderedBy: [doc("z-visible")])
                == "z-visible"
        )
    }
}
