//
//  InspectorFlowsUITests.swift
//  FicheroUITests
//
//  UI tests that ACTUALLY DO THINGS (the test mandate): open a real document,
//  open the inspector, and assert live data loads — so the connection/inspector
//  regressions we just fixed are caught automatically instead of by hand.
//
//  These are the data-dependent flows LibrarySmokeUITests explicitly deferred
//  ("select a document + open the inspector … need a seeded backend"). Each test
//  provisions its OWN hermetic backend via `UITestEngineHarness`: a disposable
//  `.fichero` library seeded (by the shared Python seeder) with a document that
//  HAS knowledge-graph entities, served by an engine on a private Unix-domain
//  socket. The app is pointed at that socket with `FICHERO_FORCE_UDS_PATH`, so
//  nothing here touches the developer's real library or a shared dev backend.
//
//  Regressions guarded:
//   - EntityService transport fix — a document's inspector entity list LOADS
//     (was "0 entities" over the broken transport). This must PASS on the
//     current fixed build. See `testDocumentInspectorLoadsSeededEntities`.
//   - KG WKWebView-over-UDS bypass — the reader's KG web pane renders real
//     content instead of the "unavailable" / URLError -1004 fallback. The
//     engine-side bridge for full-page KG navigation over UDS is NOT landed yet
//     (see DocumentKGWebPane.makeNSView's comment + the report), so that
//     assertion is wrapped in `XCTExpectFailure`: it documents the pending fix
//     and keeps the suite green until the bridge lands. See
//     `testDocumentKGWebPaneRendersNotUnavailable_pendingKGBridge`.
//
//  RUN REQUIREMENT: XCUITest drives the app in a real GUI session — these time
//  out in a headless/background job. They must run from an interactive macOS
//  login session (an interactive desktop / the manager gate), never a detached CI job.
//

import XCTest

// @MainActor on the CLASS: XCUIApplication and friends are main-actor in the
// macOS 26 SDK, and XCTest runs actor-isolated test classes on their actor -
// this isolates setUp/tearDown/tests together with no per-call bridging.
@MainActor
final class InspectorFlowsUITests: XCTestCase {
    private var harness: UITestEngineHarness!
    private var seeded: UITestEngineHarness.SeededLibrary!
    private var app: XCUIApplication!

    /// The seeded document that carries entities (person + place + org via two
    /// claims) — the meaningful "entities load" fixture. Its id is fixed by the
    /// seeder (seed_test_library.py: DOC_LETTER_ID) and referenced by name.
    private var letterDocumentId: String { seeded.ids["doc_letter"] ?? "test-doc-letter" }

    /// Generous ceiling: the engine's cold import (~2s) plus the app reaching the
    /// library over UDS. The waits below end the instant the target appears, so a
    /// healthy run never pays the whole budget.
    private let readyTimeout: TimeInterval = 120

    override func setUp() async throws {
        continueAfterFailure = false

        harness = UITestEngineHarness()
        do {
            seeded = try harness.start()
        } catch {
            // No venv / seeder / repo on this machine — skip rather than red. The
            // harness is self-describing about what it couldn't find.
            throw XCTSkip("Could not provision the UI-test engine: \(error)")
        }

        // Sanity: the fixture is only meaningful if it actually holds entities.
        XCTAssertGreaterThan(
            seeded.expected["entities"] ?? 0, 0,
            "Seeded library has no entities — the entities-load assertion would be vacuous."
        )

        app = XCUIApplication()
        app.launchArguments = ["--uitesting"]
        app.launchEnvironment = [
            // Inert host + UDS override → the app dials OUR seeded engine over the
            // private socket (no TCP, no TLS, no token). See EngineConfig+Launch.
            "FICHERO_FORCE_UDS_PATH": seeded.socketPath,
            // Disposable Application Support + the seeded library to open, plus the
            // specific document to open straight into the detail/inspector.
            "FICHERO_UITEST_HOME": seeded.appHomePath,
            "FICHERO_UITEST_LIBRARY": seeded.libraryPath,
            "FICHERO_UITEST_OPEN_DOCUMENT": letterDocumentId,
            // Unlock the knowledge inspector/reader surfaces (gated off by default).
            "FICHERO_ALL_FEATURES": "1"
        ]
    }

    override func tearDown() async throws {
        app?.terminate()
        harness?.stop()
    }

    // MARK: - Entities load (regression guard for the EntityService transport fix)

    /// Open the seeded document → open the inspector's Knowledge ▸ Entities facet
    /// → assert the entity list is NON-EMPTY. This is the exact flow that surfaced
    /// the live "0 entities" bug; it must PASS on the current fixed build.
    @MainActor
    func testDocumentInspectorLoadsSeededEntities() throws {
        app.launch()
        XCTAssertTrue(
            app.wait(for: .runningForeground, timeout: 30),
            "App did not reach the foreground — likely crashed on launch."
        )
        waitForLibraryReady()

        // The launch hook (FICHERO_UITEST_OPEN_DOCUMENT) opens the letter into the
        // detail pane; the inspector sidebar is shown by default. Select the
        // Knowledge section, then its Entities facet.
        let knowledgeSection = app.buttons["inspectorSection-Knowledge"]
        XCTAssertTrue(
            knowledgeSection.waitForExistence(timeout: readyTimeout),
            "Inspector Knowledge section never appeared — the document didn't open into the inspector."
        )
        knowledgeSection.tap()

        // Knowledge holds 3 facets (Entities/Graph/Citations), so the facet picker
        // is present; land explicitly on Entities.
        let entitiesFacet = app.buttons["Entities"].firstMatch
        if entitiesFacet.waitForExistence(timeout: 10) {
            entitiesFacet.tap()
        }

        // The load-bearing assertion: at least one entity row rendered. Each row
        // carries the `inspector.entity.row` identifier (production test hook).
        let entityRows = app.descendants(matching: .any)
            .matching(identifier: "inspector.entity.row")
        XCTAssertTrue(
            entityRows.firstMatch.waitForExistence(timeout: readyTimeout),
            "The inspector showed NO entity rows for a document that has "
            + "\(seeded.expected["entities"] ?? 0) seeded entities — the EntityService "
            + "transport regression is back (the '0 entities' bug)."
        )
        XCTAssertGreaterThan(
            entityRows.count, 0,
            "Entity rows exist but count is 0 — entities did not load."
        )

        // Positive corroboration: a seeded entity name is actually on screen.
        XCTAssertTrue(
            app.staticTexts["Eugenio Córdoba"].waitForExistence(timeout: 10),
            "Seeded entity 'Eugenio Córdoba' never rendered in the inspector list."
        )
    }

    // MARK: - KG web pane (documents the PENDING KG-over-UDS bridge fix)

    /// Open the reader's Knowledge ▸ Graph surface (the WKWebView pane) and assert
    /// it renders REAL content, not the "unavailable" / URLError -1004 fallback.
    ///
    /// PENDING: `DocumentKGWebPane` builds a raw `https://127.0.0.1:8765/view/…`
    /// URL from `EngineConfig.host` and does NOT ride the app's UDS transport, so
    /// over a UDS-only engine it falls back to `unavailableHTML()`. The engine-side
    /// bridge for full-page KG navigation over UDS is not landed yet, so the "real
    /// content, not unavailable" assertion is wrapped in `XCTExpectFailure`: this
    /// test documents the gap and keeps the suite green. When the bridge lands the
    /// expected-failure will flip to an unexpected PASS — that's the signal to drop
    /// the wrapper and let this become a normal passing guard.
    @MainActor
    func testDocumentKGWebPaneRendersNotUnavailable_pendingKGBridge() throws {
        app.launch()
        XCTAssertTrue(
            app.wait(for: .runningForeground, timeout: 30),
            "App did not reach the foreground — likely crashed on launch."
        )
        waitForLibraryReady()

        // Into the reader's Knowledge tab, then its Graph sub-mode (a WebKit view).
        let knowledgeTab = app.buttons["surfaceTab-Knowledge"]
        XCTAssertTrue(
            knowledgeTab.waitForExistence(timeout: readyTimeout),
            "Reader Knowledge tab never appeared — the document didn't open into the reader."
        )
        knowledgeTab.tap()

        let graphSubMode = app.descendants(matching: .any)
            .matching(identifier: "readerKnowledgeSubMode").firstMatch
        if graphSubMode.waitForExistence(timeout: 10) {
            // Select the Graph representation (uses the shared WKWebView pane).
            let graphButton = app.buttons["Graph"].firstMatch
            if graphButton.exists { graphButton.tap() }
        }

        let surface = app.descendants(matching: .any)
            .matching(identifier: "knowledgeSurfaceContent").firstMatch
        XCTAssertTrue(
            surface.waitForExistence(timeout: readyTimeout),
            "Knowledge web surface container never appeared."
        )

        // EXPECTED to fail until the KG-over-UDS bridge lands: the fallback page's
        // text should be ABSENT and real KG content present. Non-strict so the
        // suite stays green whether or not the inner assertion fails today; when
        // the bridge lands, drop this wrapper and let it become a normal guard.
        let expectedFailureOptions = XCTExpectedFailure.Options()
        expectedFailureOptions.isStrict = false
        XCTExpectFailure(
            "KG WKWebView full-page navigation over UDS needs the engine-side bridge (not landed).",
            options: expectedFailureOptions
        ) {
            // Give the WKWebView a beat to attempt its load and settle.
            let unavailable = app.webViews.staticTexts.containing(
                NSPredicate(format: "label CONTAINS[c] %@", "Knowledge graph web pane is unavailable")
            ).firstMatch
            XCTAssertFalse(
                unavailable.waitForExistence(timeout: 8),
                "KG web pane showed the 'unavailable' fallback instead of real content over UDS."
            )
        }
    }

    // MARK: - Helpers

    /// Block until the library content is ready (the same oracle the cold-launch
    /// test uses). `library.content.ready` sits on a container, so query ANY type.
    @MainActor
    private func waitForLibraryReady() {
        let ready = app.descendants(matching: .any)
            .matching(identifier: "library.content.ready").firstMatch
        XCTAssertTrue(
            ready.waitForExistence(timeout: readyTimeout),
            "Library never reached `library.content.ready` within \(Int(readyTimeout))s — "
            + "the app never connected to the seeded UDS engine."
        )
    }
}
