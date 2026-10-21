//
//  SharingPaneTextTests.swift
//  FicheroTests
//
//  `sharing.settings.three-panes` (#5928): Settings › Sharing's words and rules, tested without a window.
//

@testable import Fichero
import Testing

@Suite("Settings › Sharing")
struct SharingPaneTextTests {
    @Test("the status line is one grey line: where the switch lives, the error, Starting…, or what sharing is doing")
    func statusLine() {
        #expect(SharingPaneText.statusLine(isOn: true, isApplying: false, error: nil, engineIsLocal: false)
            == "Sharing is set on the Mac that runs this project")
        #expect(SharingPaneText.statusLine(isOn: true, isApplying: true, error: nil, engineIsLocal: true) == "Starting…")
        #expect(SharingPaneText.statusLine(isOn: true, isApplying: false, error: "No certificate", engineIsLocal: true) == "No certificate")
        #expect(SharingPaneText.statusLine(isOn: true, isApplying: false, error: nil, engineIsLocal: true)
            == "Sharing on your network and Tailscale")
        #expect(SharingPaneText.statusLine(isOn: false, isApplying: false, error: nil, engineIsLocal: true) == nil)
    }

    @Test("with sharing off the pane is the switch and Connect only; Devices need sharing on and a local engine")
    func devicesVisibility() {
        #expect(SharingPaneText.showsDevices(isOn: true, engineIsLocal: true))
        #expect(!SharingPaneText.showsDevices(isOn: false, engineIsLocal: true))
        #expect(!SharingPaneText.showsDevices(isOn: true, engineIsLocal: false))
    }

    @Test("a blank address is automatic; a non-https one gets the one red line")
    func addressProblem() {
        #expect(SharingPaneText.addressProblem("") == nil)
        #expect(SharingPaneText.addressProblem("  https://mac.local:8765 ") == nil)
        #expect(SharingPaneText.addressProblem("http://mac.local:8765") == "Address must start with https://")
        #expect(SharingPaneText.addressProblem("mac.local") == "Address must start with https://")
    }

    @Test("− needs a selection; the question names one device or counts several")
    func removal() {
        #expect(!SharingPaneText.canRemove(selected: 0, engineIsLocal: true))
        #expect(SharingPaneText.canRemove(selected: 2, engineIsLocal: true))
        #expect(!SharingPaneText.canRemove(selected: 2, engineIsLocal: false))
        #expect(SharingPaneText.removeQuestion(count: 1, firstName: "iPad") == "Remove iPad?")
        #expect(SharingPaneText.removeQuestion(count: 3, firstName: "iPad") == "Remove 3 devices?")
    }

    @Test("the Sharing switches name where Multi-user lives now")
    func multiUserLocation() {
        #expect(SharingToggles.location == "Settings → Sharing → Advanced")
    }

    @Test("Connect to Another Mac is there with Sharing on or off, on a host or a guest (#5893)")
    func connectIsAlwaysShown() {
        for isOn in [true, false] {
            for local in [true, false] {
                #expect(SharingPaneText.showsConnect(isOn: isOn, engineIsLocal: local), "on \(isOn), local \(local)")
            }
        }
        // and with Sharing off the pane is the switch and Connect only
        #expect(!SharingPaneText.showsDevices(isOn: false, engineIsLocal: true))
    }
}
