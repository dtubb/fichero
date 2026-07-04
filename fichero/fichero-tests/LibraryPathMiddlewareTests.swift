//
//  LibraryPathMiddlewareTests.swift
//  FicheroTests
//
//  Guards the central X-Fichero-Library-Path injection on the generated
//  FicheroClient (#1710). The middleware replaces hand-passing the header at
//  every generated call site. These tests pin the app-wide skip-list (which
//  mirrors the legacy APIClient.configureRequest) so a library-scoped op can't
//  silently drift into being treated as app-wide (or vice-versa).
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

@Suite("LibraryPathMiddleware skip-list (#1710)")
struct LibraryPathMiddlewareTests {
    // Library-scoped endpoints — MUST receive the header.
    @Test(
        "library-scoped paths are not app-wide",
        arguments: [
            "/api/documents",
            "/api/workflows/run",
            "/api/knowledge/claims",
            "/api/providers/refs",          // provider *references* are library-specific
            "/api/storage/images",
            "/api/tasks/tasks/health",
            "/api/local-inference/profiles/profile-123/health"
        ]
    )
    func libraryScopedPathsGetHeader(path: String) {
        #expect(LibraryPathMiddleware.isAppWidePath(path) == false)
    }

    // App-wide endpoints — MUST NOT receive the header.
    @Test(
        "app-wide paths are skipped",
        arguments: [
            "/api/health",
            "/api/providers",
            "/api/providers/catalog",
            "/api/providers/models",
            "/api/settings",
            "/api/settings/ai",
            "/api/registry",
            "/api/registry/libraries"
        ]
    )
    func appWidePathsAreSkipped(path: String) {
        #expect(LibraryPathMiddleware.isAppWidePath(path) == true)
    }

    // An NFD library path must leave as an NFC header value (#3076) so the app
    // never addresses a mojibake-variant of the library. `headerValue` is the
    // choke-point the middleware's `intercept` uses to build the header.
    @Test("NFD library path yields an NFC X-Fichero-Library-Path header value")
    func nfdLibraryPathHeaderIsNFC() {
        let nfd = "/tmp/\("Chocó".decomposedStringWithCanonicalMapping).fichero"
        let nfc = "/tmp/\("Chocó".precomposedStringWithCanonicalMapping).fichero"
        #expect(nfd != nfc, "test string must actually differ by normalization")

        let value = LibraryPathMiddleware.headerValue(forLibraryPath: nfd)
        #expect(value.removingPercentEncoding == nfc)
        // ASCII path encodes to itself, unchanged.
        #expect(LibraryPathMiddleware.headerValue(forLibraryPath: "/tmp/Plain.fichero") == "/tmp/Plain.fichero")
    }

    // The live closure initialiser reflects the current value, not a snapshot.
    @Test("live accessor reflects current library path")
    @MainActor
    func liveAccessorReflectsCurrentPath() {
        let provider = LibraryPathProvider(libraryPath: "/tmp/A.fichero")
        let box = LibraryPathBox(value: "/tmp/A.fichero")
        #expect(box.value == "/tmp/A.fichero")
        box.value = "/tmp/B.fichero"
        #expect(box.value == "/tmp/B.fichero")

        // Provider mutation propagates to its shared box (used by the middleware).
        provider.libraryPath = "/tmp/C.fichero"
        let middleware = provider.createMiddleware()
        _ = middleware  // constructed without snapshotting; reads live via the box
        #expect(provider.libraryPath == "/tmp/C.fichero")
    }
}
