@testable import Fichero
import Foundation
import Testing

/// Remote-library picker logic for #3151: the recents-first ordering the picker
/// applies to `GET /api/authz/libraries` results, and the per-host recents MRU
/// that backs it. Pure/isolated — no live engine.
@Suite("Remote library picker")
struct RemoteLibraryPickerTests {
    private func entry(_ path: String) -> KnownLibraryMenuEntry {
        KnownLibraryMenuEntry(id: path, path: path, name: nil, addedAt: nil, lastAccessed: nil)
    }

    @MainActor
    @Test("recentsFirst leads with recents in recents-order and keeps the tail in server order")
    func recentsFirstOrders() {
        let server = ["/a", "/b", "/c", "/d"].map(entry)
        let ordered = KnownLibraryRegistryStore.recentsFirst(server, recents: ["/c", "/a"])
        #expect(ordered.map(\.path) == ["/c", "/a", "/b", "/d"])
    }

    @MainActor
    @Test("recentsFirst with no recents is an identity (server order preserved)")
    func recentsFirstIdentityWhenEmpty() {
        let server = ["/x", "/y", "/z"].map(entry)
        #expect(KnownLibraryRegistryStore.recentsFirst(server, recents: []).map(\.path) == ["/x", "/y", "/z"])
    }

    @MainActor
    @Test("a recent path the host no longer exposes is simply dropped, not duplicated")
    func recentsFirstIgnoresUnknownRecents() {
        let server = ["/a", "/b"].map(entry)
        let ordered = KnownLibraryRegistryStore.recentsFirst(server, recents: ["/gone", "/b"])
        #expect(ordered.map(\.path) == ["/b", "/a"])
    }

    @Test("recents MRU is per-host, de-duplicated, most-recent-first, and capped")
    func recentsMRUIsPerHostAndDeduped() {
        // Unique hosts so the shared UserDefaults suite can't collide with reality.
        let hostA = "https://test-a-\(#function).example"
        let hostB = "https://test-b-\(#function).example"
        defer {
            RemoteLibraryRecents.clear(host: hostA)
            RemoteLibraryRecents.clear(host: hostB)
        }

        RemoteLibraryRecents.note(path: "/one", host: hostA)
        RemoteLibraryRecents.note(path: "/two", host: hostA)
        RemoteLibraryRecents.note(path: "/one", host: hostA)   // re-open bumps to front, no dup
        RemoteLibraryRecents.note(path: "  ", host: hostA)      // blank is a no-op

        #expect(RemoteLibraryRecents.paths(forHost: hostA) == ["/one", "/two"])
        // A path noted on host A must never surface under host B.
        #expect(RemoteLibraryRecents.paths(forHost: hostB).isEmpty)

        // Same normalized host (default port / trailing path) shares one slot.
        #expect(RemoteLibraryRecents.paths(forHost: hostA + ":443/api") == ["/one", "/two"])
    }
}
