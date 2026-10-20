//
//  AddDeviceSheetModelTests.swift
//  FicheroTests
//
//  `sharing.settings.add-device-sheet` (#5928): the one state the sheet is in and its words.
//

@testable import Fichero
import Foundation
import Testing

@Suite("Settings › Add Device sheet")
struct AddDeviceSheetModelTests {
    typealias Model = AddDeviceSheetModel

    @Test("while the app prepares, the sheet says Finishing setup and nothing else")
    func finishing() {
        #expect(Model.phase(blocker: nil, hasCode: false, hasLink: false, isWorking: true) == .finishing)
        #expect(Model.phase(blocker: .sharingNotStarted, hasCode: false, hasLink: false, isWorking: true) == .finishing)
        #expect(Model.phase(blocker: nil, hasCode: false, hasLink: false, isWorking: false) == .finishing)
    }

    @Test("a press-to-fix blocker is one Finish Setup; a stopped engine is Start")
    func presses() {
        #expect(Model.phase(blocker: .sharingNotStarted, hasCode: false, hasLink: false, isWorking: false) == .finishSetup)
        #expect(Model.phase(blocker: .pinNotDerived, hasCode: false, hasLink: false, isWorking: false) == .finishSetup)
        #expect(Model.phase(blocker: .engineNotRunning, hasCode: false, hasLink: false, isWorking: false) == .start)
    }

    @Test("a code with a link is ready; without the link Copy Link waits")
    func readyAndNotReady() {
        #expect(Model.phase(blocker: nil, hasCode: true, hasLink: true, isWorking: false) == .ready)
        #expect(Model.phase(blocker: nil, hasCode: true, hasLink: false, isWorking: false) == .notReady)
    }

    @Test("failures are one short line with no internals")
    func failures() {
        for blocker in [PairingBlocker.engineIsRemote, .addressMissing, .addressInsecure, .pinNotDerivedOnExternalEngine] {
            guard case .failed(let line) = Model.phase(blocker: blocker, hasCode: false, hasLink: false, isWorking: false) else {
                Issue.record("\(blocker) did not fail")
                continue
            }
            let lower = line.lowercased()
            #expect(!lower.contains("pin") && !lower.contains("certificate") && !lower.contains("https") && !lower.contains("restart"))
        }
    }

    @Test("the code reads in two groups; the expiry counts minutes and never shows a past time")
    func words() {
        #expect(Model.codeText("482913") == "Code 482 913")
        let now = Date()
        #expect(Model.expiresText(expiresAt: now.addingTimeInterval(600), now: now) == "Expires in 10 min")
        #expect(Model.expiresText(expiresAt: now.addingTimeInterval(30), now: now) == "Expires in under a minute")
        #expect(Model.expiresText(expiresAt: now.addingTimeInterval(-5), now: now) == "Renewing…")
    }
}
