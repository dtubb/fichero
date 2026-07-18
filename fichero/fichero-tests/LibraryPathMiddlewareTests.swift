//
//  LibraryPathMiddlewareTests.swift
//  FicheroTests
//
//  Guards the central X-Fichero-Library-Path injection on the generated
//  FicheroClient (#1710). The middleware replaces hand-passing the header at
//  every generated call site. These tests pin the app-wide skip-list so a
//  library-scoped op can't silently drift into being treated as app-wide (or
//  vice-versa).
//
//  The vice-versa direction is the expensive one (#3932): the engine 403s ANY
//  request whose library header fails _is_allowed_library_path, so an app-wide
//  endpoint that wrongly carries the header inherits a PATH failure as an AUTH
//  failure. When /auth/me, /auth/identity and /users all carried it, a bad
//  library path 403'd every probe that could have explained itself, and the app
//  raised a sign-in wall over what was really an unreadable folder.
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
            "/api/tasks/health",
            "/api/local-inference/profiles/profile-123/health",
            // /authz asks "who may do what IN THIS LIBRARY" — the engine's
            // authz.py takes require_library_path on each of these, so they 400
            // without the header. One character from /api/auth, which is skipped.
            "/api/authz/library",
            "/api/authz/members",
            "/api/authz/share"
        ]
    )
    func libraryScopedPathsGetHeader(path: String) {
        #expect(LibraryPathMiddleware.isAppWidePath(path) == false)
    }

    /// The one-character trap (#3932): `/api/auth` is app-wide and skipped,
    /// `/api/authz` is library-scoped and must NOT be. A prefix test loose enough
    /// to treat "authz" as "auth" would silently strip the header from every ACL
    /// call and 400 them all — the mirror-image of the bug being fixed.
    @Test("/api/authz is library-scoped and never confused with the app-wide /api/auth")
    func authzIsNotAuth() {
        #expect(LibraryPathMiddleware.isAppWidePath("/api/auth") == true)
        #expect(LibraryPathMiddleware.isAppWidePath("/api/auth/me") == true)
        #expect(LibraryPathMiddleware.isAppWidePath("/api/authz") == false)
        #expect(LibraryPathMiddleware.isAppWidePath("/api/authz/library") == false)
        // Same shape for the /users skip: a longer path that merely starts with
        // those characters is a different endpoint, not an app-wide one.
        #expect(LibraryPathMiddleware.isAppWidePath("/api/users") == true)
        #expect(LibraryPathMiddleware.isAppWidePath("/api/usersettings") == false)
    }

    /// The plural/singular trap (#3942): `/api/authz/libraries` (plural) lists
    /// which libraries this credential has a role on — the answer spans libraries
    /// and the engine route takes NO `require_library_path` (`authz.py:37`), so it
    /// is app-wide and must NOT carry the header. Its singular sibling
    /// `/api/authz/library` IS library-scoped and must keep it. Because the picker
    /// hits `/authz/libraries` on remote hosts where the local library path is not
    /// valid, carrying the header there would 403 the very probe that discovers
    /// what you can open — the #3932 PATH-as-AUTH cascade, one prefix over.
    @Test("/api/authz/libraries (plural) is app-wide; /api/authz/library (singular) is scoped")
    func accessibleLibrariesIsAppWideButLibraryIsNot() {
        #expect(LibraryPathMiddleware.isAppWidePath("/api/authz/libraries") == true)
        #expect(LibraryPathMiddleware.isAppWidePath("/api/authz/library") == false)
        // The exemption is anchored: it must not leak onto the scoped siblings.
        #expect(LibraryPathMiddleware.isAppWidePath("/api/authz/members") == false)
        #expect(LibraryPathMiddleware.isAppWidePath("/api/authz/share") == false)
    }

    // #2407: the exact endpoints that showed the 403→retry→200 burst on iPad are
    // all library-scoped, so the FIRST call to each carries X-Fichero-Library-Path
    // (never app-wide). Combined with warming token+session+identity before
    // markReady (AppState.confirmAuthAndLoad), the first data call is authorized —
    // no 403 flicker, no blind retry. This guards against any of them silently
    // drifting into the app-wide skip-list (which would drop the header on call #1).
    @Test(
        "the #2407 first-call-403 endpoints are library-scoped",
        arguments: [
            "/api/chains",
            "/api/documents",
            "/api/workflows",
            "/api/workflows/tools",
            "/api/chat/conversations",
            "/api/search/saved"
        ]
    )
    func issue2407EndpointsAreLibraryScoped(path: String) {
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
            "/api/registry/libraries",
            // #3942 — lists which libraries this credential has a role on; the
            // answer spans libraries, so it is app-wide (unlike singular
            // /api/authz/library, which is scoped and tested above).
            "/api/authz/libraries",
            // #3932 — "who am I" is not a library-scoped question, and accounts
            // are app-level. Every route on the engine's auth_router / users_router
            // (auth_accounts.py), none of which reads the library header.
            "/api/auth/me",
            "/api/auth/identity",
            "/api/auth/login",
            "/api/auth/logout",
            "/api/auth/invites",
            "/api/auth/invites/redeem",
            "/api/auth/sessions",
            "/api/users",
            "/api/users/user-123"
        ]
    )
    func appWidePathsAreSkipped(path: String) {
        #expect(LibraryPathMiddleware.isAppWidePath(path) == true)
    }

    /// The exact cascade #3932 fixes, pinned as one test: a bad library path 403s
    /// every request carrying the header, so while these four carried it, `/auth/me`
    /// 403'd, the `/auth/identity` fallback 403'd, `accountsExist()` 403'd, identity
    /// resolved nil, and `resolvePhase` had nothing left to conclude but
    /// `.needsLogin` — a sign-in wall over an unreadable folder. `/api/registry`
    /// answered 200 throughout only because it was already on the skip-list, which
    /// is precisely why the engine looked healthy while the app claimed otherwise.
    @Test("the identity probes that raised a false sign-in wall carry no library header")
    func identityProbesAreAppWide() {
        for path in ["/api/auth/me", "/api/auth/identity", "/api/auth/login", "/api/users"] {
            #expect(LibraryPathMiddleware.isAppWidePath(path), "\(path) must not carry the library header")
        }
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
