import Foundation

/// Pure builder/parser + MIME inference for the app's custom `fichero-server://`
/// scheme, the WebKit sibling of `fichero-res://`.
///
/// The KG reader pane renders a *whole page* the engine serves at
/// `/view/document/<id>` (and `/view/kg/global`), plus that page's relative
/// subresources (`/api/…` data + `/view/…` static assets). Loading that page as
/// a raw `https://127.0.0.1:8765/view/…` URL breaks the instant the active
/// `ClientTransport` is `.uds` (AF_UNIX socket) or in-memory: WKWebView can only
/// dial an HTTP host, so the main-frame load fails with `-1004`.
///
/// Routing the page through a `fichero-server://engine/…` URL instead lets a
/// `WKURLSchemeHandler` intercept every navigation and subresource and fetch it
/// via `FicheroClient.requestData(...)` — so the page travels whatever transport
/// the client dials, exactly like `fichero-res://` storage images. Because the
/// page's relative fetches resolve against the `fichero-server://engine` origin,
/// they route through the same handler with no per-request wiring.
///
/// This type is deliberately pure (no networking, no app types, no WebKit) so
/// its URL mapping and MIME inference are unit-testable headlessly via
/// `swift test`.
public enum EngineWebViewURL {
    /// The custom URL scheme. Non-network so `WKURLSchemeHandler` may intercept
    /// it (WebKit forbids handlers for built-in http/https).
    public static let scheme = "fichero-server"

    /// A fixed host component so the page has a well-defined same-origin base
    /// (`fichero-server://engine`); relative subresource fetches resolve against
    /// it and re-enter the handler.
    public static let host = "engine"

    /// Build `fichero-server://engine<path>` for an engine path such as
    /// `/view/document/<id>`. `path` must begin with `/` and already be
    /// percent-encoded by the caller (document ids are content hashes, but the
    /// caller encodes defensively). Returns `nil` only if the result isn't a
    /// well-formed URL.
    public static func make(path: String) -> URL? {
        URL(string: "\(scheme)://\(host)\(path)")
    }

    /// Map a `fichero-server://engine/…` URL back to the engine request path
    /// (`/view/document/<id>`, `/api/kg/graph`, `/view/static/app.js`, …).
    /// Returns `nil` for any URL of a foreign scheme or with an empty path —
    /// callers treat `nil` as "not mine", never as a silent success.
    public static func enginePath(from url: URL) -> String? {
        guard url.scheme == scheme else { return nil }
        let path = url.path
        guard !path.isEmpty else { return nil }
        return path
    }

    /// The query items carried by a `fichero-server://` URL, forwarded verbatim
    /// to the engine request (e.g. `?doc=…&mode=…`). Empty when there are none.
    public static func queryItems(from url: URL) -> [URLQueryItem] {
        URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
    }

    /// Best-effort `Content-Type` for an engine path. `requestData` returns only
    /// `(status, bytes)` — the shared transport/middleware stack does not surface
    /// the response `Content-Type` — so the handler infers it from the path, the
    /// same way `StorageResourceLoader` hard-codes content types for its known
    /// endpoints. The extension wins; then an `/api/` prefix implies JSON; then
    /// the `/view/…` page routes default to HTML.
    public static func mimeType(forPath path: String) -> String {
        let lower = path.lowercased()
        let byExtension: [(String, String)] = [
            (".js", "text/javascript; charset=utf-8"),
            (".mjs", "text/javascript; charset=utf-8"),
            (".css", "text/css; charset=utf-8"),
            (".map", "application/json"),
            (".json", "application/json"),
            (".svg", "image/svg+xml"),
            (".png", "image/png"),
            (".jpeg", "image/jpeg"),
            (".jpg", "image/jpeg"),
            (".gif", "image/gif"),
            (".webp", "image/webp"),
            (".ico", "image/x-icon"),
            (".woff2", "font/woff2"),
            (".woff", "font/woff"),
            (".ttf", "font/ttf"),
            (".html", "text/html; charset=utf-8"),
            (".htm", "text/html; charset=utf-8")
        ]
        for (suffix, mime) in byExtension where lower.hasSuffix(suffix) {
            return mime
        }
        if lower.hasPrefix("/api/") {
            return "application/json"
        }
        // `/view/document/<id>`, `/view/kg/global`, and other extension-less
        // engine page routes are server-rendered HTML.
        return "text/html; charset=utf-8"
    }
}
