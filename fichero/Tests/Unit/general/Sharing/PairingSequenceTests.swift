@testable import Fichero
import Foundation
import Testing

/// `sharing.both-clients-run-the-same-checks`, `sharing.ios-bad-library-path` (Step 2.4): one sequence, one call log.
struct PairingSequenceTests {
    private let local = "https://m.local:8765"
    private let tail = "https://m.tail1234.ts.net:8765"

    private func link(library: String? = "/Users/Shared/a/Notes.fichero") -> PairingSequence.Link {
        PairingSequence.Link(addresses: [local, tail], code: "ABCD-1234", libraryPath: library)
    }

    private func run(_ link: PairingSequence.Link, host: FakeHost, contract: String = "c1") async -> PairingSequence.Result {
        // The real clock: an answer ends the wait, so nothing here sleeps 5 seconds.
        await PairingSequence.run(link: link, host: host, ownContract: contract, ownVersion: "2026.10.28")
    }

    @Test func theCallLogIsHealthThenPairThenLibraries() async {
        let host = FakeHost()
        let result = await run(link(), host: host)
        #expect(result == .paired(url: local, libraryPath: "/Users/Shared/a/Notes.fichero"))
        #expect(await host.log == ["health m.local", "pair m.local", "authz/libraries m.local"])
    }

    @Test func anUnreadableAnswerNamesTheAddressPortAndCallNotTheDecoder() async {
        var host = FakeHost()
        host.librariesUnreadable = true
        let result = await run(link(), host: host)
        guard case .stopped(let message) = result else { Issue.record("expected stopped: \(result)"); return }
        #expect(message.hasPrefix("m.local:8765 answered its project list (GET /api/authz/libraries)"), "\(message)")
        #expect(!message.contains("correct format"))
        #expect(await host.log.last == "discard m.local", "the half-made pairing is undone")
    }

    @Test @MainActor func anAddressPastedWhereALinkGoesIsNotAPairingLink() {
        #expect {
            try RemoteClientPairing.pairingFields(fromInviteOrPayload: "10.10.10.1:8765")
        } throws: { error in
            (error as? PairingFailureError)?.failure == .invalidLink
        }
    }

    @Test func aHostThatSpellsTheSamePackageAnotherWayStillGivesIt() async {
        // Decomposed "é" in the host's list, precomposed in the link: the same package.
        let decomposed = "/Users/Shared/a/Cafe\u{301}.fichero"
        let precomposed = "/Users/Shared/a/Caf\u{e9}.fichero"
        let result = await run(link(library: precomposed), host: FakeHost(libraries: [decomposed]))
        #expect(result == .paired(url: local, libraryPath: decomposed), "the host's spelling is what it accepts")
    }

    @Test func aProjectTheHostDoesNotListIsStillNotGiven() async {
        let result = await run(link(), host: FakeHost(libraries: ["/Users/Shared/a/Other.fichero"]))
        guard case .failed(.libraryNotGiven, _) = result else { Issue.record("expected libraryNotGiven: \(result)"); return }
    }

    @Test func aContractMismatchStopsBeforeTheCodeIsSent() async {
        let host = FakeHost(contract: "c2", version: "2026.10.27")
        let result = await run(link(), host: host)
        guard case .failed(.versionMismatch, let context) = result else { Issue.record("expected a version failure: \(result)"); return }
        #expect(context.hostVersion == "2026.10.27" && context.thisVersion == "2026.10.28")
        #expect(await host.log == ["health m.local"])  // no pair
    }

    @Test func aLinkWithNoLibraryListsTheHostsAndNeverFailsBeforeTheNetwork() async {
        let one = await run(link(library: nil), host: FakeHost(libraries: ["/L1"]))
        #expect(one == .paired(url: local, libraryPath: "/L1"))
        let several = await run(link(library: nil), host: FakeHost(libraries: ["/L1", "/L2"]))
        #expect(several == .choose(url: local, libraries: ["/L1", "/L2"]))
    }

    @Test func aChoiceLeavesNoRedeemedTokenBehind() async {
        let host = FakeHost(libraries: ["/L1", "/L2"])
        _ = await run(link(library: nil), host: host)
        #expect(await host.log.last == "discard m.local")  // the token the library call needed is cleared on both sides
    }

    @Test func aHostThatSharesNothingSaysSoNotThatThisProjectWasNotGiven() async {  // t63
        let named = await run(link(), host: FakeHost(libraries: []))
        guard case .failed(.hostSharesNothing, _) = named else { Issue.record("\(named)"); return }
        let unnamed = await run(link(library: nil), host: FakeHost(libraries: []))
        guard case .failed(.hostSharesNothing, _) = unnamed else { Issue.record("\(unnamed)"); return }
        #expect(PairingFailure.hostSharesNothing.sentence(.init(host: "pro")).contains("hasn't shared any project yet"))
    }

    @Test func aNamedLibraryTheHostDoesNotGiveIsRefusedInWords() async {
        let result = await run(link(library: "/Other"), host: FakeHost(libraries: ["/L1"]))
        guard case .failed(.libraryNotGiven, _) = result else { Issue.record("\(result)"); return }
    }

    @Test func theSecondAddressIsUsedWhenTheFirstDoesNotAnswer() async {
        let host = FakeHost(dead: [local])
        let result = await run(link(), host: host)
        #expect(result == .paired(url: tail, libraryPath: "/Users/Shared/a/Notes.fichero"))
        let name = "m.tail1234.ts.net"
        #expect(await host.log == ["health m.local", "health \(name)", "pair \(name)", "authz/libraries \(name)"])
    }

    @Test func aLibraryTheHostDoesNotGiveDiscardsThePairing() async {
        let host = FakeHost(libraries: ["/L1"])
        _ = await run(link(library: "/Other"), host: host)
        #expect(await host.log.last == "discard m.local")
    }

    @Test func anErrorThatCarriesItsOwnSentenceIsPassedOnInWords() async {
        let result = await run(link(), host: FakeHost(pairErrorMessage: "This device couldn't save the connection key."))
        #expect(result == .stopped(message: "This device couldn't save the connection key."))
    }

    @Test func aRefusedCodeSaysWhichStepAndNothingIsPersisted() async {
        let result = await run(link(), host: FakeHost(pairFails: .codeUsedOrExpired))
        guard case .failed(.codeUsedOrExpired, _) = result else { Issue.record("\(result)"); return }
    }
}

private actor Log {
    private(set) var lines: [String] = []
    func add(_ line: String) { lines.append(line) }
}

private struct FakeHost: PairingSequence.Host {
    var contract = "c1"
    var version = "2026.10.28"
    var libraries = ["/Users/Shared/a/Notes.fichero"]
    var dead: [String] = []
    var pairFails: PairingFailure?
    var pairErrorMessage: String?
    var librariesUnreadable = false
    private let recorder = Log()

    init(contract: String = "c1", version: String = "2026.10.28", libraries: [String] = ["/Users/Shared/a/Notes.fichero"],
         dead: [String] = [], pairFails: PairingFailure? = nil, pairErrorMessage: String? = nil) {
        self.pairErrorMessage = pairErrorMessage
        self.contract = contract
        self.version = version
        self.libraries = libraries
        self.dead = dead
        self.pairFails = pairFails
    }

    var log: [String] { get async { await recorder.lines } }

    func health(at url: String) async -> (failure: PairingFailure?, health: PairingSequence.HostHealth?) {
        await recorder.add("health \(PairingAddressTry.host(url))")
        return dead.contains(url) ? (.nameNotFound, nil) : (nil, .init(contract: contract, version: version))
    }

    func pair(at url: String, code: String) async throws {
        await recorder.add("pair \(PairingAddressTry.host(url))")
        if let pairFails { throw pairFails }
        if let pairErrorMessage { throw MessageError(message: pairErrorMessage) }
    }

    func discardPairing(at url: String) async {
        await recorder.add("discard \(PairingAddressTry.host(url))")
    }

    func libraries(at url: String) async throws -> [String] {
        await recorder.add("authz/libraries \(PairingAddressTry.host(url))")
        if librariesUnreadable {
            throw DecodingError.dataCorrupted(.init(codingPath: [], debugDescription: "not the shape the client expects"))
        }
        return libraries
    }
}

private struct MessageError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}
