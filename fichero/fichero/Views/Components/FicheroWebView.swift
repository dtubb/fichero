import FicheroAPIClient
import SwiftUI
import WebKit

/// A reusable `WKWebView` wrapper for plain in-app browsing surfaces.
///
/// This is the shared, minimal WebKit representable: it loads whatever URL the
/// bound `urlString` points at, reports loading state and page title back to the
/// host, and keeps `urlString` in sync as the user follows links. It deliberately
/// carries no auth headers, user-script injection, or JS message bridge — those
/// belong to specialized surfaces (e.g. `DocumentKGWebPane`, which keeps its own
/// `GuardedWKWebView` + coordinator for the KG document viewer).
///
/// Surfaces that need a browser chrome (address bar, Save-to-Library, etc.) build
/// that chrome themselves and host this view underneath — see `ResearchBrowserPane`.
#if os(macOS)
struct FicheroWebView: NSViewRepresentable {
    @Binding var urlString: String
    @Binding var pageTitle: String
    @Binding var isLoading: Bool

    func makeCoordinator() -> FicheroWebViewCoordinator { FicheroWebViewCoordinator(self) }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        // Let embedded `fichero-res://` storage images resolve through the
        // generated client (transport-agnostic), rather than a raw engine URL.
        config.setURLSchemeHandler(StorageResourceSchemeHandler(), forURLScheme: StorageResourceURL.scheme)
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        context.coordinator.webView = webView
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        let target = context.coordinator.lastLoadedURL
        if target != urlString, let url = URL(string: urlString), url.scheme != nil {
            context.coordinator.lastLoadedURL = urlString
            webView.load(URLRequest(url: url))
        }
    }
}
#elseif os(iOS) || os(visionOS)
struct FicheroWebView: UIViewRepresentable {
    @Binding var urlString: String
    @Binding var pageTitle: String
    @Binding var isLoading: Bool

    func makeCoordinator() -> FicheroWebViewCoordinator { FicheroWebViewCoordinator(self) }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        // Let embedded `fichero-res://` storage images resolve through the
        // generated client (transport-agnostic), rather than a raw engine URL.
        config.setURLSchemeHandler(StorageResourceSchemeHandler(), forURLScheme: StorageResourceURL.scheme)
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        context.coordinator.webView = webView
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        let target = context.coordinator.lastLoadedURL
        if target != urlString, let url = URL(string: urlString), url.scheme != nil {
            context.coordinator.lastLoadedURL = urlString
            webView.load(URLRequest(url: url))
        }
    }
}
#endif

@MainActor
final class FicheroWebViewCoordinator: NSObject, WKNavigationDelegate {
    var parent: FicheroWebView
    weak var webView: WKWebView?
    var lastLoadedURL: String = ""

    init(_ parent: FicheroWebView) {
        self.parent = parent
    }

    func webView(_ webView: WKWebView, didStartProvisionalNavigation navigation: WKNavigation!) {
        parent.isLoading = true
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        parent.isLoading = false
        parent.pageTitle = webView.title ?? ""
        if let currentURL = webView.url?.absoluteString {
            lastLoadedURL = currentURL
            parent.urlString = currentURL
        }
    }

    /// Validate engine TLS against the persisted SPKI pin when the web view is
    /// loading the configured engine host. Non-engine traffic falls back to the
    /// system trust evaluation so external browsing keeps working (#2601).
    @MainActor
    func webView(
        _ webView: WKWebView,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping @MainActor @Sendable (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        guard let engineHost = EngineConfig.host.host?.lowercased(),
              challenge.protectionSpace.host.lowercased() == engineHost else {
            completionHandler(.performDefaultHandling, nil)
            return
        }
        let (disposition, credential) = RemoteCertificatePinning.resolveServerTrustChallenge(challenge)
        completionHandler(disposition, credential)
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: any Error) {
        parent.isLoading = false
    }
}
