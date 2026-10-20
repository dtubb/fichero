//
//  EngineRestartSaysWhyTests.swift
//  FicheroTests
//
//  `activity.engine.restart-says-why`: when the app restarts its engine because the health checks went unanswered,
//  the connection detail says so in words, with how long, not only "stopped responding".
//

@testable import Fichero
import Testing

@MainActor
@Suite("Engine restart says why")
struct EngineRestartSaysWhyTests {
    @Test("the sentence names the seconds missed, and an import when one was running")
    func sentenceNamesSeconds() {
        let plain = AppState.restartSentence(failures: 2, busyWithImport: false)
        #expect(plain.contains("about 10 seconds"))
        #expect(!plain.contains("importing"))
        #expect(AppState.restartSentence(failures: 8, busyWithImport: true).contains("while importing"))
    }

    @Test("an app-managed failure detail carries the reason, and falls back to the old sentence without one")
    func detailCarriesReason() {
        let reason = AppState.restartSentence(failures: 2, busyWithImport: false)
        let with = ConnectionPresentation.failureDetail(
            accessError: .engineUnreachable, authBroken: false, ownership: .appManaged, restartReason: reason
        )
        #expect(with.hasPrefix(reason) && with.hasSuffix("Reconnecting…"))
        let without = ConnectionPresentation.failureDetail(
            accessError: .engineUnreachable, authBroken: false, ownership: .appManaged, restartReason: nil
        )
        #expect(without == "Fichero's engine stopped responding. Reconnecting…")
    }
}
