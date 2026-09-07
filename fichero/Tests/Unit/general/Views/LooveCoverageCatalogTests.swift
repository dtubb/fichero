@testable import Fichero
import XCTest

/// The loove coverage window lets a user choose ANY language to test, not just
/// the fixed modern/historical toggles. These tests cover the catalog logic that
/// backs the searchable picker and the persistence layer: a freely-chosen code
/// must be found by search, resolve to a stable column, and survive the
/// @AppStorage round-trip — the old menu-only path silently dropped any code
/// outside the curated `all` list.
final class LooveCoverageCatalogTests: XCTestCase {

    // MARK: - Search

    func test_search_finds_language_by_name() {
        let hits = LanguageCatalog.search("swahili")
        XCTAssertTrue(hits.contains { $0.code == "sw" }, "Swahili should be searchable by name")
    }

    func test_search_finds_language_by_code() {
        let hits = LanguageCatalog.search("FA")
        XCTAssertTrue(hits.contains { $0.code == "fa" }, "Persian should be searchable by ISO code, case-insensitively")
    }

    func test_search_empty_query_returns_whole_catalog() {
        XCTAssertEqual(LanguageCatalog.search("   ").count, LanguageCatalog.searchable.count)
    }

    func test_search_no_match_is_empty() {
        XCTAssertTrue(LanguageCatalog.search("zznotalanguage").isEmpty)
    }

    func test_searchable_is_deduplicated_and_curated_first() {
        let codes = LanguageCatalog.searchable.map(\.code)
        XCTAssertEqual(Set(codes).count, codes.count, "No duplicate codes across curated + ISO")
        // A curated entry wins over the plain ISO one (e.g. Coptic keeps its
        // curated spelling), and the curated set leads the list.
        XCTAssertEqual(LanguageCatalog.searchable.first?.code, LanguageCatalog.modern.first?.code)
    }

    // MARK: - Choosing an arbitrary language adds a stable column

    func test_choosing_arbitrary_language_adds_a_column() {
        // "sw" is NOT in the fixed modern/historical toggles, only in the broader
        // ISO catalog — exactly the free-choice case.
        XCTAssertFalse(LanguageCatalog.all.contains { $0.code == "sw" })

        let columns = LanguageCatalog.languages(for: ["en", "sw"])
        XCTAssertEqual(columns.map(\.code), ["en", "sw"], "Chosen language becomes a column in stable order")
        XCTAssertEqual(columns.last?.name, "Swahili")
    }

    func test_offcatalog_code_is_preserved_as_honest_passthrough() {
        // A code we know nothing about must NOT vanish — it shows as its own
        // column so the engine can honestly report unknown for it.
        let columns = LanguageCatalog.languages(for: ["xyz"])
        XCTAssertEqual(columns.map(\.code), ["xyz"])
        XCTAssertEqual(columns.first?.name, "XYZ")
    }

    func test_language_lookup_resolves_known_and_passes_through_unknown() {
        XCTAssertEqual(LanguageCatalog.language(for: "cop").name, "Coptic")
        XCTAssertEqual(LanguageCatalog.language(for: "unknowncode").name, "UNKNOWNCODE")
    }

    // MARK: - Persistence round-trip

    func test_ordered_codes_preserve_arbitrary_choice() {
        // Simulate the @AppStorage comma-list round-trip the view performs.
        let chosen: Set<String> = ["ru-petr1708", "en", "sw", "cop"]
        let raw = LanguageCatalog.orderedCodes(chosen).joined(separator: ",")
        let restored = Set(raw.split(separator: ",").map(String.init))
        XCTAssertEqual(restored, chosen, "Every chosen code — including the arbitrary 'sw' — survives")
        // Order is stable (catalog order), not selection order.
        let codes = raw.split(separator: ",").map(String.init)
        XCTAssertLessThan(
            codes.firstIndex(of: "en")!, codes.firstIndex(of: "sw")!,
            "Curated 'en' precedes ISO-only 'sw' in the stable column order"
        )
    }
}
