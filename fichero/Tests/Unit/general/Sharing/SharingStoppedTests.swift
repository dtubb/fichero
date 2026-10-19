//
//  SharingStoppedTests.swift
//  FicheroTests
//
//  sharing.off-closes-the-guest (#5731): the host's typed `sharing.stopped` event ends the guest's
//  stream for good and says one sentence. See docs/contributor_manual/specs/transport/library-sharing.md.
//

@testable import Fichero
import Foundation
import Testing

@MainActor
struct SharingStoppedTests {
    private struct Stub: ChangeStreamTransport {
        var frames: [String]
        func connect(_ request: URLRequest) async throws
            -> (status: Int, lines: AsyncThrowingStream<String, any Error>) {
            let frames = frames
            return (200, AsyncThrowingStream { continuation in
                for frame in frames { continuation.yield(frame) }
                continuation.finish()
            })
        }
    }

    private func stream(_ frames: [String]) -> LibraryChangeStream {
        LibraryChangeStream(
            baseURL: URL(string: "https://host.test:8765")!, libraryPath: "/lib", windowId: "w",
            transport: Stub(frames: frames)
        )
    }

    @Test func theStoppedEventMarksTheStreamAndCallsBackOnce() async throws {
        let guest = stream(["data:{\"type\":\"sharing.stopped\"}", "data:{\"type\":\"sharing.stopped\"}"])
        var calls = 0
        guest.onSharingStopped = { calls += 1 }
        try await guest.subscribeOnce(resyncOnConnect: false)
        #expect(guest.sharingStopped)
        #expect(calls == 1)
    }

    @Test func anOrdinaryEventDoesNotStopTheStream() async throws {
        let guest = stream(["data:{\"type\":\"entity.updated\"}"])
        try await guest.subscribeOnce(resyncOnConnect: false)
        #expect(!guest.sharingStopped)
    }

    @Test func theSentenceNamesTheHost() {
        #expect(SharingStopped.sentence(host: "Studio") == "Studio stopped sharing this library.")
        #expect(SharingStopped.sentence(host: "") == "The host stopped sharing this library.")
    }
}
