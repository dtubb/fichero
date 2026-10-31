#if os(macOS)
import XCTest

/// Settings › Sharing on the Mac, against the harness's seeded embedded engine (Multi-user off by default):
/// `sharing.people-pane-off-state` (#5917) and `sharing.card-keeps-its-code` (#5915), from
/// docs/contributor_manual/specs/source/sharing-two-macs.md §10.2 and §10.4. WRITTEN 2026-10-31, NOT RUN (no xcodebuild on the
/// builder's Mac); listed in fichero-ui-mac.xctestplan. Navigation follows the real view tree: ⌘, opens Settings, the sidebar's
/// "Sharing" row, then the pane's section picker ("People" / "Devices").
@MainActor
final class SharingPaneUITests: FicheroUISessionTests {
    private func openSharing(section: String) throws {
        waitForLibraryReady()
        app.typeKey(",", modifierFlags: .command)
        let sharingRow = app.staticTexts["Sharing"].firstMatch
        try XCTSkipUnless(sharingRow.waitForExistence(timeout: 10), "Settings did not open or has no Sharing row")
        sharingRow.click()
        let picker = app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", section)).firstMatch
        try XCTSkipUnless(picker.waitForExistence(timeout: 10), "the Sharing pane has no \(section) section")
        picker.click()
    }

    /// Multi-user off (the seeded engine's default): no `+`, the line, the Open Sharing button; the button lands on Devices.
    func testPeopleOffStateHidesAdd() throws {
        try openSharing(section: "People")
        let line = app.staticTexts["people.multiuserOff"]
        XCTAssertTrue(line.waitForExistence(timeout: 10), "the People pane does not say Multi-user is off")
        XCTAssertTrue(line.label.hasPrefix("Multi-user is off."), "unexpected words: \(line.label)")
        XCTAssertFalse(app.buttons["accounts.add"].exists, "the + is offered while Multi-user is off: Create Account would 404")
        let hop = app.buttons["people.openSharing"]
        XCTAssertTrue(hop.exists, "no way to the switch from the People pane")
        hop.click()
        XCTAssertTrue(app.switches.matching(NSPredicate(format: "label CONTAINS %@", "Sharing")).firstMatch.waitForExistence(timeout: 10),
                      "Open Sharing did not land on the Devices section (the Sharing switch)")
    }

    /// With Sharing on, the Add Device sheet offers both address rows: This network with the host, and Tailscale (enabled with a
    /// host when the harness Mac has it, else greyed with why and no host; never a placeholder host, review M2).
    func testAddDeviceSheetShowsBothAddressRows() throws {
        try openSharing(section: "Devices")
        let sharing = app.switches.matching(NSPredicate(format: "label CONTAINS %@", "Sharing")).firstMatch
        XCTAssertTrue(sharing.waitForExistence(timeout: 10), "the Devices section has no Sharing switch: the pane is broken, not skipped")
        if (sharing.value as? String) != "1" { sharing.click() }
        let add = app.buttons["Add Device…"]
        try XCTSkipUnless(add.waitForExistence(timeout: 60) && add.isEnabled, "Sharing did not come up in time (certificate + restart)")
        add.click()
        let thisNetwork = app.descendants(matching: .any).matching(identifier: "sharing.address.row.this-network").firstMatch
        let tailscale = app.descendants(matching: .any).matching(identifier: "sharing.address.row.tailscale").firstMatch
        XCTAssertTrue(thisNetwork.waitForExistence(timeout: 30), "no This network row")
        XCTAssertTrue(tailscale.exists, "no Tailscale row (it must be there, greyed with why, even without Tailscale)")
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "tailscale.invalid")).firstMatch.exists,
                       "a placeholder host is shown")
        XCTAssertTrue(app.buttons["sharing.address.copy.this-network"].exists, "This network has no Copy of its own")
        app.buttons["Done"].click()
    }

    /// With Sharing on, the code on the Add Device sheet survives a health check (a Multi-user flip runs one). The flip reaches only
    /// the harness's own engine: `FicheroUISessionTests` runs the app against a disposable Application Support root under a unique temp
    /// directory (`UITestEngineHarness`, FICHERO_UITEST_HOME), never the person's (review L3).
    func testCodeSurvivesAHealthCheck() throws {
        try openSharing(section: "Devices")
        let sharing = app.switches.matching(NSPredicate(format: "label CONTAINS %@", "Sharing")).firstMatch
        XCTAssertTrue(sharing.waitForExistence(timeout: 10), "the Devices section has no Sharing switch: the pane is broken, not skipped")
        if (sharing.value as? String) != "1" { sharing.click() }
        let add = app.buttons["Add Device…"]
        try XCTSkipUnless(add.waitForExistence(timeout: 60) && add.isEnabled, "Sharing did not come up in time (certificate + restart)")
        add.click()
        let expires = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Expires")).firstMatch
        XCTAssertTrue(expires.waitForExistence(timeout: 30), "no code on the Add Device sheet")
        let codeBefore = app.staticTexts.matching(NSPredicate(format: "label MATCHES %@", "^[A-Z0-9]{4}(-[A-Z0-9]{4})+$")).firstMatch.label
        app.buttons["Done"].click()
        // A Multi-user flip calls checkBackendHealth(); the refused flip (no owner password) is still a health check.
        let multiuser = app.switches.matching(NSPredicate(format: "label CONTAINS %@", "Multi-user")).firstMatch
        XCTAssertTrue(multiuser.waitForExistence(timeout: 10), "no Multi-user switch in Advanced: the pane is broken, not skipped")
        multiuser.click()
        sleep(3)
        add.click()
        XCTAssertTrue(expires.waitForExistence(timeout: 10), "the card lost its code after a health check")
        let codeAfter = app.staticTexts.matching(NSPredicate(format: "label MATCHES %@", "^[A-Z0-9]{4}(-[A-Z0-9]{4})+$")).firstMatch.label
        XCTAssertEqual(codeBefore, codeAfter, "the code was re-minted by a health check (`sharing.card-keeps-its-code`)")
        app.buttons["Done"].click()
    }
}
#endif
