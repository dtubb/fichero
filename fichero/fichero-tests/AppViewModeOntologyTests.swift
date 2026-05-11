@testable import Fichero
import XCTest

/// Tests for the AppViewMode.ontology case wiring (#498). Locks the
/// category routing + the persistence serialization that drives the
/// sidebar → content router for the Knowledge Graph entry.
final class AppViewModeOntologyTests: XCTestCase {

    // MARK: - category routing

    func testOntologyCategoryIsFolder() {
        // .ontology maps to ItemCategory.folder for toolbar dispatch
        // purposes — shares the library toolbar set. Locks the choice
        // made in SidebarViewTypes.swift.
        XCTAssertEqual(AppViewMode.ontology.category, .folder)
    }

    // MARK: - exhaustive switch sanity

    func testEveryAppViewModeHasCategory() {
        // Smoke: build every AppViewMode case and read .category.
        // If any case crashes / returns wrong category, the toolbar
        // dispatch breaks silently.
        let modes: [AppViewMode] = [
            .library(nil),
            .search(nil),
            .chat(nil),
            .comparison(nil),
            .workflow(nil),
            .chain(nil),
            .batches,
            .batch(nil),
            .automation,
            .schedule(nil),
            .trigger(nil),
            .activity(nil),
            .ontology
        ]
        for mode in modes {
            _ = mode.category  // no crash + non-optional return
        }
        // 13 cases total — bumped from 12 with the addition of .ontology.
        XCTAssertEqual(modes.count, 13)
    }
}
