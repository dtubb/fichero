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
struct FicheroWebView: NSViewRepresentable {
    @Binding var urlString: String
    @Binding var pageTitle: String
    @Binding var isLoading: Bool

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
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

    @MainActor
    class Coordinator: NSObject, WKNavigationDelegate {
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

        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: any Error) {
            parent.isLoading = false
        }
    }
}
