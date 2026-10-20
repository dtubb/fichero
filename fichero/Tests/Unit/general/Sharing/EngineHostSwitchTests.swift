//
//  EngineHostSwitchTests.swift
//  FicheroTests
//
//  sharing.one-writer-of-the-engine-host (#5916): one procedure changes the engine host, whichever screen asks.
//  See docs/contributor_manual/specs/transport/library-sharing.md.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
struct EngineHostSwitchTests {
    private final class Log {
        var steps: [String] = []
        var host = "previous"
        var answers = true
        var startFails = 0
    }

    private func make(_ log: Log) -> EngineHostSwitch {
        EngineHostSwitch(
            stop: { log.steps.append("stop") },
            setHost: { log.host = $0; log.steps.append("set \($0)") },
            repoint: { log.steps.append("repoint") },
            start: {
                log.steps.append("start")
                if log.startFails > 0 { log.startFails -= 1; throw URLError(.cannotConnectToHost) }
            },
            reconnect: { log.steps.append("reconnect"); return log.answers },
            onRestoreFailure: { _ in log.steps.append("restore failed") }
        )
    }

    @Test func aNewHostStopsWritesRepointsStartsAndReconnectsInThatOrder() async throws {
        let log = Log()
        try await make(log).run(from: "previous", to: "new", notResponding: "no answer")
        #expect(log.steps == ["stop", "set new", "repoint", "start", "reconnect"])
        #expect(log.host == "new")
    }

    @Test func aHostThatDoesNotAnswerIsRolledBackToThePreviousOne() async {
        let log = Log()
        log.answers = false
        await #expect(throws: EngineHostSwitchError.self) {
            try await make(log).run(from: "previous", to: "new", notResponding: "no answer",
                                    onFailure: { log.steps.append("failed \($0)") })
        }
        #expect(log.host == "previous")
        #expect(log.steps == ["stop", "set new", "repoint", "start", "reconnect", "failed new",
                              "stop", "set previous", "repoint", "start", "reconnect"])
    }

    @Test func aHostThatWillNotStartIsRolledBackAndTheStartErrorIsThrown() async {
        let log = Log()
        log.startFails = 1
        await #expect(throws: URLError.self) {
            try await make(log).run(from: "previous", to: "new", notResponding: "no answer")
        }
        #expect(log.host == "previous")
    }

    @Test func ifEvenThePreviousHostWillNotStartTheCallerIsTold() async {
        let log = Log()
        log.startFails = 2
        await #expect(throws: URLError.self) {
            try await make(log).run(from: "previous", to: "new", notResponding: "no answer")
        }
        #expect(log.steps.last == "restore failed")
    }

    @Test func anUnchangedHostOnlyRepointsTheClients() async throws {
        let log = Log()
        try await make(log).run(from: "same", to: "same", notResponding: "no answer")
        #expect(log.steps == ["repoint"], "no needless engine restart")
    }

    @Test func theNotRespondingSentenceIsTheCallers() async {
        let log = Log()
        log.answers = false
        do {
            try await make(log).run(from: "previous", to: "new", notResponding: "Paired, but the host is not responding.")
            Issue.record("expected a throw")
        } catch {
            #expect(error.localizedDescription == "Paired, but the host is not responding.")
        }
    }
}
