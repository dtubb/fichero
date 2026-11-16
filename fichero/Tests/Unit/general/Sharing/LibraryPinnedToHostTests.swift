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

    @Test func openingASharedLibraryAddsAPinnedOneBesideTheLocalOnesAndKeepsTheRest() throws {
        let manager = LibraryManager.shared
        let before = manager.openLibraries.map(\.id)
        let current = manager.currentLibraryId
        defer {
            manager.openLibraries.removeAll { !before.contains($0.id) }
            manager.currentLibraryId = current
        }
        let path = "/Volumes/Archive/Pinned Beside \(UUID().uuidString)"
        let opened = try #require(manager.switchToRemoteLibrary(path: path, pinnedTo: studio))
        #expect(opened.pinnedToHost)
        #expect(opened.host.url == studio)
        #expect(manager.currentLibraryId == opened.id)
        #expect(before.allSatisfy { id in manager.openLibraries.contains { $0.id == id } })
        #expect(manager.switchToRemoteLibrary(path: path, pinnedTo: studio)?.id == opened.id)
    }

    @Test func servicesBuiltFromAPinnedLibrarysClientDialItsHostNotTheAppHost() {
        let pinned = library(pinned: true)
        #expect(ActivityService(apiClient: pinned.apiClient).client.baseURL == studio)
        #expect(ArtifactService(apiClient: pinned.apiClient).client.baseURL == studio)
        #expect(RenditionService(apiClient: pinned.apiClient).client.baseURL == studio)
        #expect(ImportService(apiClient: pinned.apiClient).client.baseURL == studio)
    }

    @Test func aPinnedLibraryIsSavedApartFromTheLocalPaths() throws {
        let manager = LibraryManager.shared
        let defaults = EngineConfig.defaults
        let savedLocal = defaults.object(forKey: LibraryManager.openLibraryPathsKey)
        let savedPinned = defaults.object(forKey: LibraryManager.pinnedLibrariesKey)
        let before = manager.openLibraries.map(\.id)
        let current = manager.currentLibraryId
        defer {
            manager.openLibraries.removeAll { !before.contains($0.id) }
            manager.currentLibraryId = current
            defaults.set(savedLocal, forKey: LibraryManager.openLibraryPathsKey)
            defaults.set(savedPinned, forKey: LibraryManager.pinnedLibrariesKey)
        }
        let path = "/Volumes/Archive/Saved Apart \(UUID().uuidString)"
        _ = try #require(manager.switchToRemoteLibrary(path: path, pinnedTo: studio))
        #expect(defaults.stringArray(forKey: LibraryManager.openLibraryPathsKey)?.contains(path) != true)
        let pinned = defaults.array(forKey: LibraryManager.pinnedLibrariesKey) as? [[String: String]] ?? []
        #expect(pinned.contains { $0["host"] == studio.absoluteString && $0["path"] == path })
    }

    @Test func restoreReopensASavedSharedLibraryBesideTheLocalOnesForAPairedHostOnly() {
        let manager = LibraryManager.shared
        let defaults = EngineConfig.defaults
        let savedLocal = defaults.object(forKey: LibraryManager.openLibraryPathsKey)
        let savedPinned = defaults.object(forKey: LibraryManager.pinnedLibrariesKey)
        let before = manager.openLibraries.map(\.id)
        let current = manager.currentLibraryId
        defer {
            manager.openLibraries.removeAll { !before.contains($0.id) }
            manager.currentLibraryId = current
            defaults.set(savedLocal, forKey: LibraryManager.openLibraryPathsKey)
            defaults.set(savedPinned, forKey: LibraryManager.pinnedLibrariesKey)
        }
        let kept = "/Volumes/Archive/Restore Kept \(UUID().uuidString)"
        let unpaired = "/Volumes/Archive/Restore Dropped \(UUID().uuidString)"
        let saved = [["host": studio.absoluteString, "path": kept], ["host": "https://gone.local:8765", "path": unpaired]]
        manager.restorePinnedLibraries(saved: saved, paired: [studio.absoluteString])
        #expect(manager.openLibraries.contains { $0.url.path == kept && $0.pinnedToHost && $0.host.url == studio })
        #expect(!manager.openLibraries.contains { $0.url.path == unpaired })
        #expect(manager.currentLibraryId == current)
    }

    @Test func aSharedLibraryThatWouldNotOpenIsDroppedFromTheSavedListToo() throws {
        let manager = LibraryManager.shared
        let defaults = EngineConfig.defaults
        let savedLocal = defaults.object(forKey: LibraryManager.openLibraryPathsKey)
        let savedPinned = defaults.object(forKey: LibraryManager.pinnedLibrariesKey)
        let before = manager.openLibraries.map(\.id)
        let current = manager.currentLibraryId
        defer {
            manager.openLibraries.removeAll { !before.contains($0.id) }
            manager.currentLibraryId = current
            defaults.set(savedLocal, forKey: LibraryManager.openLibraryPathsKey)
            defaults.set(savedPinned, forKey: LibraryManager.pinnedLibrariesKey)
        }
        let path = "/Volumes/Archive/Would Not Open \(UUID().uuidString)"
        let opened = try #require(manager.switchToRemoteLibrary(path: path, pinnedTo: studio))
        manager.dropPinnedLibrary(opened.id, backTo: current)
        #expect(!manager.openLibraries.contains { $0.id == opened.id })
        #expect(manager.currentLibraryId == current)
        let saved = defaults.array(forKey: LibraryManager.pinnedLibrariesKey) as? [[String: String]] ?? []
        #expect(!saved.contains { $0["path"] == path })
    }
}
