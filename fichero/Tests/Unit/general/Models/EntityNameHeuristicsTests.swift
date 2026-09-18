@testable import Fichero
import Foundation
import XCTest

/// Tests for `EntityNameHeuristics.isOcrGarbage` (#4705 increment 3: moved
/// out of `OntologyBrowser` — the KG sidebar mode retired, but this
/// heuristic has a real caller in `LibraryView+FilterAndBatch.swift` and
/// survives independently of it).
final class EntityNameHeuristicsTests: XCTestCase {

    func testIsOcrGarbageRejectsSingleCharacter() {
        XCTAssertTrue(EntityNameHeuristics.isOcrGarbage("x"))
    }

    func testIsOcrGarbageRejectsNumericOnly() {
        XCTAssertTrue(EntityNameHeuristics.isOcrGarbage("12345"))
    }

    func testIsOcrGarbageAcceptsNormalName() {
        XCTAssertFalse(EntityNameHeuristics.isOcrGarbage("Eugenio Córdoba"))
    }

    func testIsOcrGarbageRejectsTimestampFormat() {
        // "12:10" is the exact pattern reported in #2482 — pure digits + colon, zero letters.
        XCTAssertTrue(EntityNameHeuristics.isOcrGarbage("12:10"))
    }

    func testIsOcrGarbageRejectsBboxFragment() {
        XCTAssertTrue(EntityNameHeuristics.isOcrGarbage("0.42:0.87"))
    }

    func testIsOcrGarbageAcceptsAlphanumericMix() {
        // Names like "Section 12" or "COVID-19" contain letters and must not be filtered.
        XCTAssertFalse(EntityNameHeuristics.isOcrGarbage("Section 12"))
        XCTAssertFalse(EntityNameHeuristics.isOcrGarbage("COVID-19"))
    }
}
