//
//  LibraryPinnedToHostTests.swift
//  FicheroTests
//
//  sharing.guest.library-pinned-to-its-host (#6360, #2866): a library pinned to a paired Mac dials that Mac, and the
//  app-wide host switch and an engine restart never repoint it; a library that is not pinned follows the app host.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@MainActor
struct LibraryPinnedToHostTests {
    private let studio = URL(string: "https://studio.local:8765")!

    private func library(pinned: Bool) -> LibraryManager.LibraryReference {
        LibraryManager.LibraryReference(
            url: URL(fileURLWithPath: "/Volumes/Archive/Isthima GHG"), document: FicheroDocument(),
            displayName: "Isthima GHG", host: BackendHost(url: studio, tokenKind: .remote), pinnedToHost: pinned)
    }

    @Test func aPinnedLibraryDialsItsOwnHostOverHTTPS() {
        let (url, transport) = library(pinned: true).currentEndpoint
        #expect(url == studio)
        #expect(transport == .https)
    }

    @Test func aPinnedLibraryKeepsItsHostThroughTheAppWideSwitch() {
        let pinned = library(pinned: true)
        pinned.reconfigureBackendHost()
        pinned.reresolveEndpoint()
        #expect(pinned.ficheroClient.baseURL == studio)
        #expect(pinned.apiClient.baseURL == studio.appendingPathComponent("api"))
    }

    @Test func aLibraryThatIsNotPinnedFollowsTheAppHost() {
        let (url, transport) = library(pinned: false).currentEndpoint
        #expect(url == EngineConfig.host)
        #expect(transport == EngineConfig.transportMode)
    }

    @Test func aPinnedLibraryReadsAsRemoteInTheSidebar() {
        #expect(library(pinned: true).locationDescriptor.isLocal == false)
    }
}
