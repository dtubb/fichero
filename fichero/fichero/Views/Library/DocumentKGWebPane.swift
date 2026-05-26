import FicheroAPIClient
import SwiftUI
import WebKit

enum DocumentKGPaneRoute {
    static let baseURL = "http://localhost:8765"

    static func documentURL(documentId: String) -> URL? {
        guard let encoded = documentId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) else {
            return nil
        }
        return URL(string: "\(baseURL)/view/document/\(encoded)")
    }

    static func request(documentId: String, libraryPath: String) -> URLRequest? {
        guard let url = documentURL(documentId: documentId) else { return nil }
        var request = URLRequest(url: url)
        request.addEngineAuth(libraryPath: libraryPath)
        return request
    }

    static func bootstrapScript(token: String?, libraryPath: String) -> String {
        let tokenLiteral = jsStringLiteral(token ?? "")
        let libraryLiteral = jsStringLiteral(libraryPath)
        return """
        window.ficheroToken = '\(tokenLiteral)';
        window.ficheroLibrary = '\(libraryLiteral)';
        """
    }

    static func jsStringLiteral(_ raw: String) -> String {
        raw
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "'", with: "\\'")
            .replacingOccurrences(of: "\r", with: "")
            .replacingOccurrences(of: "\n", with: "\\n")
    }
}

struct DocumentKGWebPane: NSViewRepresentable {
    let documentId: String
    let libraryPath: String
    var selectedClaimId: String?
    var activePageNumber: Int?
    var onEntitySelected: (String, String?) -> Void = { _, _ in }
    var onClaimSelected: (String, String?, String?) -> Void = { _, _, _ in }

    func makeCoordinator() -> Coordinator {
        Coordinator(parent: self)
    }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        let controller = config.userContentController
        controller.add(context.coordinator, name: "ficheroBridge")
        controller.addUserScript(
            WKUserScript(
                source: DocumentKGPaneRoute.bootstrapScript(
                    token: AuthTokenMiddleware.readTokenFromDisk(),
                    libraryPath: libraryPath
                ),
                injectionTime: .atDocumentStart,
                forMainFrameOnly: true
            )
        )

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.setValue(false, forKey: "drawsBackground")
        context.coordinator.loadIfNeeded(webView)
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        context.coordinator.parent = self
        context.coordinator.injectContext(into: webView)
        context.coordinator.loadIfNeeded(webView)
        context.coordinator.syncSelection(into: webView)
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        var parent: DocumentKGWebPane

        private var lastLoadedDocumentId: String?
        private var lastLoadedLibraryPath: String?
        private var lastSelectedClaimId: String?
        private var lastActivePageNumber: Int?

        init(parent: DocumentKGWebPane) {
            self.parent = parent
        }

        func loadIfNeeded(_ webView: WKWebView) {
            guard
                lastLoadedDocumentId != parent.documentId || lastLoadedLibraryPath != parent.libraryPath,
                let request = DocumentKGPaneRoute.request(
                    documentId: parent.documentId,
                    libraryPath: parent.libraryPath
                )
            else { return }

            lastLoadedDocumentId = parent.documentId
            lastLoadedLibraryPath = parent.libraryPath
            webView.load(request)
        }

        func injectContext(into webView: WKWebView) {
            let script = DocumentKGPaneRoute.bootstrapScript(
                token: AuthTokenMiddleware.readTokenFromDisk(),
                libraryPath: parent.libraryPath
            )
            webView.evaluateJavaScript(script)
        }

        func syncSelection(into webView: WKWebView) {
            if lastSelectedClaimId != parent.selectedClaimId {
                lastSelectedClaimId = parent.selectedClaimId
                if let claimId = parent.selectedClaimId {
                    let literal = DocumentKGPaneRoute.jsStringLiteral(claimId)
                    webView.evaluateJavaScript("window.fichero?.highlightClaim('\(literal)');")
                }
            }

            if lastActivePageNumber != parent.activePageNumber {
                lastActivePageNumber = parent.activePageNumber
                if let pageNumber = parent.activePageNumber {
                    webView.evaluateJavaScript("window.fichero?.setActivePage(\(pageNumber));")
                }
            }
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            injectContext(into: webView)
            syncSelection(into: webView)
        }

        func userContentController(
            _ userContentController: WKUserContentController,
            didReceive message: WKScriptMessage
        ) {
            guard
                message.name == "ficheroBridge",
                let body = message.body as? [String: Any],
                let kind = body["kind"] as? String
            else { return }

            switch kind {
            case "entitySelected":
                guard let entityId = body["entityId"] as? String else { return }
                parent.onEntitySelected(entityId, body["sourceDocumentId"] as? String)
            case "claimSelected":
                guard let claimId = body["claimId"] as? String else { return }
                parent.onClaimSelected(
                    claimId,
                    body["sourceDocumentId"] as? String,
                    body["passage"] as? String
                )
            default:
                break
            }
        }
    }
}
