//
//  ServerAdvancedModelTests.swift
//  FicheroTests
//
//  `sharing.settings.three-panes`, `sharing.settings.server-url-one-writer` (#5928, #5916): the Server pane's words, and the
//  Server URL field commits only through the one engine-host writer.
//

@testable import Fichero
import Testing

@MainActor
@Suite("Settings › Server")
struct ServerAdvancedModelTests {
    private struct Refused: LocalizedError { var errorDescription: String? { "That address did not answer, so the previous one is back." } }

    @Test("status is one word; Restart needs a local engine that is not already restarting")
    func statusAndRestart() {
        #expect(ServerSettingsText.status(running: true) == "Running")
        #expect(ServerSettingsText.status(running: false) == "Stopped")
        #expect(ServerSettingsText.canRestart(isRestarting: false, engineIsLocal: true))
        #expect(!ServerSettingsText.canRestart(isRestarting: true, engineIsLocal: true))
        #expect(!ServerSettingsText.canRestart(isRestarting: false, engineIsLocal: false))
    }

    @Test("the clients line names each client once, and is absent when nobody connected")
    func clientsLine() {
        #expect(ServerSettingsText.clientsLine([]) == nil)
        #expect(ServerSettingsText.clientsLine(["app", "fichero CLI", "app", "MCP"]) == "app · fichero CLI · MCP")
    }

    @Test("a blank address is the built-in engine; a non-https one gets the one red line")
    func addressProblem() {
        #expect(ServerSettingsText.addressProblem("https://pro.local:8765") == nil)
        #expect(ServerSettingsText.addressProblem("http://pro.local:8765") == "Address must start with https://")
    }

    @Test("Return hands the draft to the one writer, from the stored host, and writes nothing itself")
    func commitGoesThroughTheOneWriter() async {
        let model = ServerAdvancedModel()
        model.sync(stored: "https://old.local:8765")
        model.draft = "https://new.local:8765"
        var calls: [(String, String, String)] = []
        await model.commit(stored: "https://old.local:8765") { calls.append(($0, $1, $2)) }
        #expect(calls.count == 1)
        #expect(calls.first?.0 == "https://old.local:8765" && calls.first?.1 == "https://new.local:8765")
        #expect(calls.first?.2 == "That address did not answer, so the previous one is back.")
        #expect(model.error == nil)
    }

    @Test("an unchanged address asks the writer to repoint and read health again, with its own words")
    func unchangedAddress() async {
        let model = ServerAdvancedModel()
        model.draft = "https://pro.local:8765"
        var said = ""
        await model.commit(stored: "https://pro.local:8765") { _, _, notResponding in said = notResponding }
        #expect(said == "The engine did not answer.")
    }

    @Test("an invalid address never reaches the writer; a writer's refusal is shown in its words")
    func invalidAndRefused() async {
        let model = ServerAdvancedModel()
        model.draft = "http://insecure.local"
        var called = false
        await model.commit(stored: "") { _, _, _ in called = true }
        #expect(!called)
        model.draft = "https://gone.local:8765"
        await model.commit(stored: "") { _, _, _ in throw Refused() }
        #expect(model.error == "That address did not answer, so the previous one is back.")
    }
}
