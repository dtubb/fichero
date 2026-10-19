//
//  SharedProjectRowTests.swift
//  FicheroTests
//
//  sharing.sidebar.guest-row (#5737): a shared project is a Projects row with a small shared mark,
//  and the Inspector names the host. See docs/contributor_manual/specs/transport/library-sharing.md.
//

@testable import Fichero
import Foundation
import Testing

struct SharedProjectRowTests {
    @Test func aRemoteHostGetsTheSharedMarkAndNamesTheHost() throws {
        let host = BackendHost(url: try #require(URL(string: "https://studio.local:8765")))
        let descriptor = LibraryLocationDescriptor.forHost(host)
        #expect(!descriptor.isLocal)
        #expect(descriptor.systemImage == "person.2")
        #expect(descriptor.label == "Shared from studio.local")
    }

    @Test func thisMacsOwnProjectCarriesNoSharedMark() throws {
        let host = BackendHost(url: try #require(URL(string: "https://127.0.0.1:8765")))
        let descriptor = LibraryLocationDescriptor.forHost(host)
        #expect(descriptor.isLocal)
        #expect(descriptor.systemImage != "person.2")
    }
}
