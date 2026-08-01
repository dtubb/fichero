import XCTest

/// Source-surface tests for #4422 — the inspector Attributes strip showed
/// internal bookkeeping (`Ingest COPY`, a storage `Path`, filesystem
/// `Created`/`Modified` dates) by default, alongside the one genuinely
/// useful line (`Entities`). Daniel: show none of these by default.
///
/// Two changes:
///   1. The fixed attributes (status/kind/created/modified) flip from
///      opt-OUT (`hiddenRaw`, default empty → everything shows) to opt-IN
///      (`shownAttributesRaw`, default empty → nothing shows) — the same
///      polarity the KG/artifact/metadata rows already used. `DisplayAttribute`
///      was the one inconsistent case.
///   2. `ingest` and `path` are removed from the enum entirely — storage
///      internals, not user-facing facts about the document, same class as
///      #4416 (island) and #4398 (list row).
///
/// Entities-as-lozenges (the other half of #4422) is NOT done here — it's a
/// rendering change cross-referenced to #4394 and needs a live build to
/// verify, which isn't available under the no-builds-for-workers rule.
final class DisplayAttributesStripDefaultsTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testFixedAttributesDefaultToNoneShown() throws {
        let source = try Self.appSource("Views/Inspector/DisplayAttributesStrip.swift")
        XCTAssertTrue(
            source.contains(#"@AppStorage("inspector.attributeStrip.shown") var shownAttributesRaw: String = """#),
            "the fixed-attribute visibility key must default to empty (nothing shown)"
        )
        // The old opt-out key/name must be gone, not just unused — a stray
        // reference would mean two sources of truth for the same rows.
        XCTAssertFalse(source.contains("hiddenRaw"))
        XCTAssertFalse(source.contains("inspector.attributeStrip.hidden"))
    }

    func testShouldRenderRequiresExplicitOptIn() throws {
        let source = try Self.appSource("Views/Inspector/DisplayAttributesStrip+Menu.swift")
        XCTAssertTrue(source.contains("shownAttributes.contains(attr.rawValue)"))
        XCTAssertFalse(source.contains("hiddenAttributes"))
    }

    func testIngestAndPathAreNotAvailableAttributesAtAll() throws {
        let source = try Self.appSource("Views/Inspector/DisplayAttributesStrip+Attributes.swift")
        XCTAssertTrue(source.contains("case status, kind, created, modified"))
        XCTAssertFalse(source.contains("case ingest"))
        // "case status, kind, ingest" or similar — belt and braces against a
        // reformatted case list re-adding them.
        XCTAssertFalse(source.contains(", ingest"))
        XCTAssertFalse(source.contains(", path"))
    }

    func testNoSurfaceStillRendersIngestOrPathRows() throws {
        let source = try Self.appSource("Views/Inspector/DisplayAttributesStrip+Rows.swift")
        XCTAssertFalse(source.contains("case .ingest"))
        XCTAssertFalse(source.contains("case .path"))
        XCTAssertFalse(source.contains("document.path ?? \"\""))
    }

    func testIngestValueComputedPropertyWasRemovedNotOrphaned() throws {
        // A dead computed property reading `document.isLinked` for a row
        // nothing renders any more is exactly the kind of leftover that
        // looks like coverage but isn't.
        let source = try Self.appSource("Views/Inspector/DisplayAttributesStrip+Values.swift")
        XCTAssertFalse(source.contains("var ingestValue"))
    }

    func testEntitiesStillSurfaceByDefault() throws {
        // The one row the issue calls genuinely useful must survive the
        // default-to-nothing change — this is #2696's existing default,
        // untouched by #4422.
        let source = try Self.appSource("Views/Inspector/DisplayAttributesStrip.swift")
        XCTAssertTrue(
            source.contains(#"@AppStorage("inspector.attributeStrip.kg") var shownKGRaw: String = "entities""#)
        )
    }
}
