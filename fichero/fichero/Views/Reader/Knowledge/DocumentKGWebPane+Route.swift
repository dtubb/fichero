import FicheroAPIClient
import Foundation

extension DocumentKGPaneRoute {
    static let globalKGDocumentID = "__kg_global__"

    /// The KG page loads over the custom `fichero-engine://engine` origin, NOT a
    /// raw `https://…:8765` URL. `EngineWebViewSchemeHandler` intercepts every
    /// navigation + relative subresource and fetches it through the transport-
    /// agnostic `FicheroClient`, so the whole page works over `.https`, `.uds`,
    /// and in-memory transports alike (a raw engine URL fails `-1004` over UDS
    /// because WKWebView can only dial an HTTP host).
    static var baseURL: String {
        "\(EngineWebViewURL.scheme)://\(EngineWebViewURL.host)"
    }

    static func documentURL(documentId: String) -> URL? {
        guard let encoded = documentId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) else {
            return nil
        }
        return URL(string: "\(baseURL)/view/document/\(encoded)")
    }

    /// The `FicheroClient` whose transport the KG page's scheme handler funnels
    /// through — the open library matching `libraryPath`, falling back to the
    /// Global library. Its `currentLibraryPath` is already set to `libraryPath`,
    /// so `requestData` applies the correct library scoping automatically.
    @MainActor
    static func webViewClient(libraryPath: String, libraryManager: LibraryManager) -> FicheroClient? {
        if let match = libraryManager.openLibraries.first(where: { $0.url.path == libraryPath }) {
            return match.ficheroClient
        }
        return libraryManager.globalLibrary?.ficheroClient
    }

    static func supportsAuthenticatedWebView() -> Bool {
        let host = EngineConfig.host
        if !RemoteCertificatePinning.shouldEnforcePinning(for: host) {
            return true
        }
        return RemoteCertificatePinning.persistedSPKIPin(hostString: host.absoluteString) != nil
    }

    static func request(documentId: String, libraryPath: String) -> URLRequest? {
        guard supportsAuthenticatedWebView() else {
            return nil
        }
        let url: URL?
        if documentId == globalKGDocumentID {
            url = URL(string: "\(baseURL)/view/kg/global")
        } else {
            url = documentURL(documentId: documentId)
        }
        guard let url else { return nil }
        // No auth headers here: `EngineWebViewSchemeHandler` re-issues every load
        // through `FicheroClient.requestData`, whose middleware stack applies the
        // auth token + `X-Fichero-Library-Path`. Headers set on this request are
        // not forwarded by the handler.
        _ = libraryPath
        return URLRequest(url: url)
    }

    static func unavailableHTML() -> String {
        """
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <style>
            /* Semantic palette matching document_view.html so this fallback page
               reads as the same app in light AND dark (#3683), even though the
               theme-injection script doesn't run on this standalone HTML. */
            :root { --bg: #f7f4ee; --text: #1f1d1a; --muted: #6a6258; }
            @media (prefers-color-scheme: dark) {
              :root { --bg: #1e1b18; --text: #ece7df; --muted: #a59b8d; }
            }
            body {
              font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif;
              margin: 0; background: var(--bg); color: var(--text);
            }
            main { max-width: 34rem; margin: 0 auto; padding: 2rem 1.25rem; }
            h1 { font-size: 1.1rem; margin: 0 0 0.75rem; }
            p { line-height: 1.45; color: var(--muted); margin: 0.5rem 0; }
          </style>
        </head>
        <body>
          <main>
            <h1>Knowledge graph web pane is unavailable for remote hosts.</h1>
            <p>Authenticated KG pages use WKWebView, which does not participate in Fichero's pinned remote transport.</p>
            <p>Reconnect to the embedded local engine to use this pane.</p>
          </main>
        </body>
        </html>
        """
    }

    static func bootstrapScript(token: String?, libraryPath: String) -> String {
        let tokenLiteral = jsStringLiteral(token ?? "")
        let libraryLiteral = jsStringLiteral(libraryPath)
        return """
        (function() {
            var nativeToken = '\(tokenLiteral)';
            var nativeTokenSentinel = '__fichero_native_token__';
            window.ficheroToken = nativeTokenSentinel;
            window.ficheroLibrary = '\(libraryLiteral)';
            if (window.ficheroNativeFetchInstalled) { return; }
            window.ficheroNativeFetchInstalled = true;
            var nativeFetch = window.fetch.bind(window);
            window.fetch = function(input, init) {
                var requestURL = typeof input === 'string' ? input : input?.url;
                var url = new URL(requestURL || '', window.location.href);
                var nextInit = init ? Object.assign({}, init) : {};
                var headers = new Headers(nextInit.headers || (input && input.headers) || {});
                if (url.origin === window.location.origin
                    && headers.get('Authorization') === 'Bearer ' + nativeTokenSentinel) {
                    headers.set('Authorization', 'Bearer ' + nativeToken);
                    nextInit.headers = headers;
                }
                return nativeFetch(input, nextInit);
            };
            try {
                Object.defineProperty(window, 'fetch', {
                    value: window.fetch,
                    writable: false,
                    configurable: false
                });
            } catch (sealError) {
                // Older WebKit that rejects redefining fetch: the override still
                // applies, it just stays re-wrappable. Non-fatal.
            }
        })();
        """
    }

    static func shouldRefreshBootstrapScript(
        hasCachedScript: Bool,
        cachedLibraryPath: String?,
        libraryPath: String,
        force: Bool
    ) -> Bool {
        force || !hasCachedScript || cachedLibraryPath != libraryPath
    }
}
