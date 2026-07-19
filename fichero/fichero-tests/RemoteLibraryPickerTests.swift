@testable import Fichero
import Foundation
import Testing

/// Remote-library picker logic for #3151: the recents-first ordering the picker
/// applies to `GET /api/authz/libraries` results, and the per-host recents MRU
/// that backs it. Pure/isolated — no live engine.
// .serialized: the recents tests mutate one shared UserDefaults.standard key
// (fichero.remote.recentLibraries) via a non-atomic read-modify-write, so running
// them in parallel loses updates and flakes the MRU order. Serialize the suite so
// each test's recents mutations complete before the next runs (#4016). The
// most-recent-first ordering itself (production RemoteLibraryRecents.note) is correct.
@Suite("Remote library picker", .serialized)
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

    @Test("recents MRU is capped at 12, evicting the oldest")
    func recentsMRUCapsAtTwelve() {
        let host = "https://test-cap-\(#function).example"
        defer { RemoteLibraryRecents.clear(host: host) }

        for index in 0..<15 { RemoteLibraryRecents.note(path: "/lib\(index)", host: host) }
        let paths = RemoteLibraryRecents.paths(forHost: host)
        #expect(paths.count == 12)
        #expect(paths.first == "/lib14")        // most-recent kept
        #expect(!paths.contains("/lib2"))        // oldest three evicted
    }

    @Test("menu-entry display name trims, else falls back to the path's last component")
    func displayNameTrimsElseFallsBackToPath() {
        func named(_ name: String?) -> KnownLibraryMenuEntry {
            KnownLibraryMenuEntry(id: "1", path: "/x/Archive.fichero", name: name, addedAt: nil, lastAccessed: nil)
        }
        #expect(named("  My Library  ").displayName == "My Library")
        #expect(named("   ").displayName == "Archive")   // blank → path stem
        #expect(named(nil).displayName == "Archive")
    }
}
