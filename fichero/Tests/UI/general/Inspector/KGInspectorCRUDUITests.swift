//
//  KGInspectorCRUDUITests.swift
//  FicheroUITests
//
//  UI-test coverage for the KG inspector's entity CRUD affordances, pinned to
//  docs/contributor_manual/specs/kg/kg-tables.md (Behaviors B/C/D) and driven
//  per docs/contributor_manual/specs/testing/ui-testing-strategy.md: stable
//  data-ID-anchored accessibility identifiers, `waitForExistence`/`XCTWaiter`
//  (never sleeps or poll-until-deadline), each flow ending with
//  `try app.performAccessibilityAudit()`.
//
//  Runs on the SHARED session (FicheroUISessionTests, #4246) — same seeded
//  engine + app instance every other functional suite drives. Mutations here
//  are PERMANENT for the rest of the run (no per-test reset hook yet, see
//  FicheroUISession.swift), so this suite is careful to only mutate a seeded
//  entity nothing else depends on:
//    - "Eugenio Córdoba" is asserted by InspectorFlowsUITests — NEVER delete it.
//    - "Ministry of Education" and "Bogotá" are unreferenced elsewhere in the
//      Swift UI suites (checked via search_text before writing this file) —
//      safe to mutate/delete.
//
//  RUN REQUIREMENT: same as InspectorFlowsUITests — a real GUI session
//  (interactive macOS login / the manager gate), never headless/detached CI.
//

import XCTest

@MainActor
final class KGInspectorCRUDUITests: FicheroUISessionTests {

    // MARK: - Navigation (mirrors InspectorFlowsUITests' path to the tab)

    /// Open the seeded document's inspector Knowledge ▸ Entities facet — the
    /// same path `InspectorFlowsUITests.testDocumentInspectorLoadsSeededEntities`
    /// uses, so this suite starts from an already-verified-reachable surface.
    private func navigateToKnowledgeEntities() {
        let knowledgeSection = app.buttons["inspectorSection-Knowledge"]
        XCTAssertTrue(
            knowledgeSection.waitForExistence(timeout: readyTimeout),
            "Inspector Knowledge section never appeared — the document didn't open into the inspector."
        )
        knowledgeSection.tap()

        let entitiesFacet = app.buttons["Entities"].firstMatch
        if entitiesFacet.waitForExistence(timeout: 10) {
            entitiesFacet.tap()
        }

        // Sanity: at least one entity row rendered before driving CRUD on it.
        let entityRows = app.descendants(matching: .any)
            .matching(identifier: "inspector.entity.row")
        XCTAssertTrue(
            entityRows.firstMatch.waitForExistence(timeout: readyTimeout),
            "No entity rows rendered — cannot drive CRUD against an empty table."
        )
    }

    // MARK: - B. Entity CRUD (#4624)

    /// spec: kg-tables.md Behavior B, `kg.tables.entity.delete` [OK].
    ///
    /// Right-click the seeded "Ministry of Education" entity row, invoke
    /// "Delete…" from the context menu (`kg.entity.menu.delete`, added by this
    /// change in DocumentInspectorEntitiesTab+Menus.swift), confirm the alert
    /// (`kg.entity.delete.confirm`, added in DocumentInspectorEntitiesTab.swift),
    /// and assert the row is gone. Targets "Ministry of Education" — NOT
    /// "Eugenio Córdoba", which `InspectorFlowsUITests` depends on staying
    /// present in the shared session.
    func testEntityDeleteRemovesRow() throws {
        waitForLibraryReady()
        navigateToKnowledgeEntities()

        let targetName = "Ministry of Education"
        // Target the ROW uniquely: the entity list tags each row `inspector.entity.row`
        // (one per entity); match the one whose text is our target. A bare name query
        // is ambiguous — the detail pane also renders the title as plain static text.
        let row = app.staticTexts.matching(
            NSPredicate(format: "identifier == %@ AND (value == %@ OR label == %@)",
                        "inspector.entity.row", targetName, targetName)
        ).firstMatch
        XCTAssertTrue(
            row.waitForExistence(timeout: readyTimeout),
            "Seeded entity '\(targetName)' never rendered as an inspector row."
        )

        row.click()       // select the row so the context menu targets it
        row.rightClick()

        let deleteMenuItem = app.menuItems["kg.entity.menu.delete"]
        XCTAssertTrue(
            deleteMenuItem.waitForExistence(timeout: 5),
            "Context menu 'Delete…' item (kg.entity.menu.delete) never appeared."
        )
        deleteMenuItem.tap()

        // The confirm button carries a stable identifier (`kg.entity.delete.confirm`,
        // set on the alert in DocumentInspectorEntitiesTab). `app.buttons[id]`
        // traverses every window the app owns — including the separate window
        // macOS presents a SwiftUI `.alert` in — so this is the correct query
        // regardless of where the alert is hosted. (The old query matched a window
        // *containing a button whose identifier is "Cancel"*, but the Cancel button's
        // "Cancel" is its LABEL, not its identifier — it could never match.)
        let confirmDelete = app.buttons["kg.entity.delete.confirm"].firstMatch
        if !confirmDelete.waitForExistence(timeout: 10) {
            attachScreenshot(named: "delete-confirm-missing")
        }
        XCTAssertTrue(
            confirmDelete.exists,
            "Delete confirmation alert's 'Delete' button never appeared "
            + "(screenshot attached; windows=\(app.windows.count), dialogs=\(app.dialogs.count), sheets=\(app.sheets.count))."
        )
        confirmDelete.tap()

        // No `waitForNonExistence` on XCUIElement — poll via XCTWaiter's own
        // NSPredicate expectation, Apple's sanctioned non-sleep primitive
        // (distinct from the retired hand-rolled poll-until-deadline pattern).
        let goneExpectation = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "exists == false"),
            object: row
        )
        let result = XCTWaiter().wait(for: [goneExpectation], timeout: readyTimeout)
        XCTAssertEqual(
            result, .completed,
            "'\(targetName)' row still exists after confirming delete."
        )

        try app.performAccessibilityAudit()
    }

    /// spec: kg-tables.md Behavior B, `kg.tables.entity.retype` [OK] — entity
    /// type is editable by dragging one entity onto a DIFFERENT-kind entity
    /// (`DocumentInspectorEntitiesTab+Actions.swift.handleEntityDrop` →
    /// `PendingEntityReclassifyPlan` → the `kg.entity.retype.confirm` alert
    /// button). A cross-kind drop retypes the DRAGGED entity to the TARGET's
    /// kind; a same-kind drop is a merge instead (asserted elsewhere).
    ///
    /// Requires the shared fixture to seed DISTINCT entity kinds — `Bogotá`
    /// (location), `Eugenio Córdoba` (person), `Ministry of Education`
    /// (organization). Before seed_test_library.py set explicit `entity_type`s
    /// they all defaulted to `.other`, landing in one kind-section, so every
    /// drop resolved to a same-kind merge and this path was unreachable. The
    /// seeder now types them, so dragging the location onto the person reaches
    /// the reclassify confirmation for real.
    ///
    /// This test proves the affordance is REACHABLE and the confirmation is
    /// presented; it CANCELS rather than confirms, so it does not mutate the
    /// shared session's kind diversity that later drops depend on.
    func testEntityRetypeChangesType() throws {
        waitForLibraryReady()
        navigateToKnowledgeEntities()

        let sourceName = "Bogotá"          // seeded location
        let targetName = "Eugenio Córdoba" // seeded person — different kind
        let source = app.staticTexts[sourceName]
        let target = app.staticTexts[targetName]
        XCTAssertTrue(source.waitForExistence(timeout: readyTimeout), "'\(sourceName)' never rendered.")
        XCTAssertTrue(target.waitForExistence(timeout: 10), "'\(targetName)' never rendered.")

        source.press(forDuration: 0.6, thenDragTo: target)

        let retypeConfirm = app.buttons["kg.entity.retype.confirm"].firstMatch
        if !retypeConfirm.waitForExistence(timeout: 5) {
            attachScreenshot(named: "retype-confirm-missing")
        }
        XCTAssertTrue(
            retypeConfirm.exists,
            "No 'Change Type' confirmation (kg.entity.retype.confirm) appeared after dragging "
            + "'\(sourceName)' (location) onto '\(targetName)' (person) — the cross-kind "
            + "reclassify path was not reached "
            + "(screenshot attached; windows=\(app.windows.count), dialogs=\(app.dialogs.count), sheets=\(app.sheets.count))."
        )

        // Cancel — proving reachability without mutating the shared fixture.
        let cancelButton = app.buttons["Cancel"].firstMatch
        if cancelButton.waitForExistence(timeout: 3) {
            cancelButton.tap()
        }

        try app.performAccessibilityAudit()
    }

    // MARK: - D. Cross-cutting: accessibility (ui-testing.a11y-audit)

    /// spec: ui-testing-strategy.md, `ui-testing.a11y-audit` [MISSING until this
    /// test] — every XCUITest flow ends with `performAccessibilityAudit()`
    /// (Apple-first-party); this test's whole job is running that audit over
    /// the Knowledge inspector's Entities facet, where this suite's CRUD
    /// affordances (`kg.entity.menu.*`, `kg.entity.delete`, `kg.entity.curate.*`)
    /// live. Adopting this is the first step toward retiring
    /// `check_accessibility.py` (spec ruling 1 — audit first, retire second).
    func testKnowledgeInspectorAccessibilityAudit() throws {
        waitForLibraryReady()
        navigateToKnowledgeEntities()

        try app.performAccessibilityAudit()
    }

    // MARK: - Diagnostics

    /// Attach a full-screen screenshot to the test report. Called only on a
    /// failing branch so a green run carries no attachments. Cheap and targeted
    /// — never dump the XCUI element tree (`allElementsBoundByIndex` /
    /// `debugDescription`), which OOMs the runner.
    private func attachScreenshot(named name: String) {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
