import Foundation
import HTTPTypes
import OpenAPIRuntime

/// Middleware that adds the `X-Fichero-Library-Path` header to every
/// library-scoped request on the generated `FicheroClient`.
///
/// This is the generated-client counterpart to the legacy `APIClient`'s
/// `configureRequest` (`Services/APIClient.swift`). Before this existed, the
/// header was passed BY HAND at every generated call site
/// (`headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")`),
/// which is error-prone: required ops 422/fail-to-compile when forgotten,
/// optional ops silently 422 or return wrong-library data (#1710, #1666).
///
/// **One source of truth for "is this endpoint app-wide?"** — the skip-list
/// in `isAppWidePath(_:)` mirrors the legacy `configureRequest` exactly
/// (health / providers-except-refs / settings / registry). Keep the two in
/// sync; the goal is to eventually delete the legacy one.
///
/// **Library path is read LIVE on every request** (via the `currentLibraryPath`
/// closure), not snapshotted at construction. This mirrors how
/// `AuthTokenMiddleware` reads its token fresh on each request, and means the
/// header always reflects the client's *current* `currentLibraryPath` even if
/// it changes between requests.
public struct LibraryPathMiddleware: ClientMiddleware {
    /// Live accessor for the current library path. Returns `nil` (header
    /// omitted) when no library is loaded.
    private let currentLibraryPath: @Sendable () -> String?

    /// Construct with a fixed library path (used by tests / direct callers).
    public init(libraryPath: String? = nil) {
        self.currentLibraryPath = { libraryPath }
    }

    /// Construct with a live accessor so the header reflects the client's
    /// current library path at request time rather than a snapshot.
    public init(currentLibraryPath: @escaping @Sendable () -> String?) {
        self.currentLibraryPath = currentLibraryPath
    }

    /// App-wide endpoints that must NOT carry the `X-Fichero-Library-Path`
    /// header. Mirrors `APIClient.configureRequest` exactly:
    /// - `/health` — readiness probe, no library yet.
    /// - `/providers` (except `/providers/refs`) — provider catalogue is global;
    ///   provider *references* are library-specific and DO get the header.
    /// - `/settings` — app-wide settings.
    /// - `/registry` — the known-library registry is GLOBAL (one registry of all
    ///   `.fichero` packages), not scoped to any one library (#1661).
    public static func isAppWidePath(_ path: String) -> Bool {
        let isHealth = matchesRootPath(path, allowedPath: "/api/health")
        let isAppWideProvider = matchesRootPath(path, allowedPath: "/api/providers")
            && !matchesRootPath(path, allowedPath: "/api/providers/refs")
        let isSettings = matchesRootPath(path, allowedPath: "/api/settings")
        let isRegistry = matchesRootPath(path, allowedPath: "/api/registry")
        return isHealth || isAppWideProvider || isSettings || isRegistry
    }

    private static func matchesRootPath(_ path: String, allowedPath: String) -> Bool {
        path == allowedPath || path.hasPrefix("\(allowedPath)/")
    }

    /// The exact `X-Fichero-Library-Path` value produced for `libraryPath`:
    /// NFC-normalized (#3076) so the header never carries an NFD mojibake
    /// variant, then percent-encoded (#2648) so non-ASCII survives the latin-1
    /// header transport. Extracted so the normalization is unit-testable without
    /// the HTTP plumbing. `.urlPathAllowed` mirrors `urllib.parse.quote(path,
    /// safe="/")`; the engine `unquote`s on read (api/library_header.py).
    public static func headerValue(forLibraryPath libraryPath: String) -> String {
        let normalized = libraryPath.nfcNormalized
        return normalized.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? normalized
    }

    public func intercept(
        _ request: HTTPRequest,
        body: HTTPBody?,
        baseURL: URL,
        operationID: String,
        next: (HTTPRequest, HTTPBody?, URL) async throws -> (HTTPResponse, HTTPBody?)
    ) async throws -> (HTTPResponse, HTTPBody?) {
        var request = request
        let path = request.path ?? ""

        // Library-scoped endpoints get the header (overwrite, not append) when a
        // library is loaded. App-wide endpoints, or a nil/empty path, leave it
        // absent — matching the legacy behaviour (and its warning log).
        if !Self.isAppWidePath(path),
           let libraryPath = currentLibraryPath(),
           !libraryPath.isEmpty {
            // Normalize (NFC, #3076) + percent-encode (#2648) via the shared
            // choke-point helper so every request carries the canonical bytes the
            // backend expects (#3071) and no duplicate variant is ever addressed.
            request.headerFields[.init("X-Fichero-Library-Path")!] =
                Self.headerValue(forLibraryPath: libraryPath)
        }

        return try await next(request, body, baseURL)
    }
}

/// Thread-safe holder for the current library path so `LibraryPathMiddleware`
/// can read it live from any executor without hopping to the main actor.
public final class LibraryPathBox: @unchecked Sendable {
    private let lock = NSLock()
    private var _value: String?

    public init(value: String? = nil) {
        self._value = value
    }

    public var value: String? {
        get {
            lock.lock()
            defer { lock.unlock() }
            return _value
        }
        set {
            lock.lock()
            _value = newValue
            lock.unlock()
        }
    }
}

/// Owns the live library path and vends a `LibraryPathMiddleware` bound to it.
///
/// `FicheroClient` keeps one of these and updates `libraryPath` whenever its
/// `currentLibraryPath` changes; the middleware created via `createMiddleware()`
/// reads the value live through a shared `LibraryPathBox`, so requests always
/// carry the current path.
@MainActor
public final class LibraryPathProvider: ObservableObject {
    @Published public var libraryPath: String? {
        didSet { box.value = libraryPath }
    }

    private let box: LibraryPathBox

    public init(libraryPath: String? = nil) {
        self.box = LibraryPathBox(value: libraryPath)
        self.libraryPath = libraryPath
    }

    /// Creates a middleware that reads this provider's current library path
    /// live (not a snapshot) via the shared box.
    public func createMiddleware() -> LibraryPathMiddleware {
        let box = self.box
        return LibraryPathMiddleware(currentLibraryPath: { box.value })
    }
}
