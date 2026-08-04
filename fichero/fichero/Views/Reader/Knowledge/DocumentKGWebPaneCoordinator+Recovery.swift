import Foundation
import WebKit

// Renderer-death recovery for the reader's KG web pane, both platforms.
//
// The renderer dies for reasons outside the app — memory pressure, sandbox
// bootstrap races, GPU resets (iOS jetsams WebContent far more readily than
// macOS). Without this callback the pane stays blank until the user changes
// documents. Recovery reloads the SAME document through `loadIfNeeded`
// (clearing its dedupe keys first, so it actually fires), within the bounded
// budget `WebContentProcessRecovery` enforces — a crash-looping renderer ends
// at an honest failure page instead of a reload storm.
//
// Two identical bodies rather than a protocol: the coordinators are separate
// platform classes by design (#4373), and the shared logic — the budget — is
// already extracted into `WebContentProcessRecovery`.

#if canImport(AppKit)
extension DocumentKGWebPaneCoordinatorMacOS {
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        let reload = WebContentProcessRecovery.shouldReload(&processRecovery)
        webContentRecoveryLogger.error(
            """
            Reader WebContent process terminated for document \
            \(self.lastLoadedDocumentId ?? "nil", privacy: .public); \
            \(reload ? "reloading" : "reload budget exhausted", privacy: .public)
            """
        )
        guard reload else {
            webView.loadHTMLString(
                DocumentKGPaneRoute.loadFailureHTML(
                    detail: "The reader's rendering process keeps terminating."
                ),
                baseURL: nil
            )
            return
        }
        lastLoadedDocumentId = nil
        lastLoadedLibraryPath = nil
        loadIfNeeded(webView)
    }
}
#elseif canImport(UIKit)
extension DocumentKGWebPaneCoordinatoriOS {
    func webViewWebContentProcessDidTerminate(_ webView: WKWebView) {
        let reload = WebContentProcessRecovery.shouldReload(&processRecovery)
        webContentRecoveryLogger.error(
            """
            Reader WebContent process terminated for document \
            \(self.lastLoadedDocumentId ?? "nil", privacy: .public); \
            \(reload ? "reloading" : "reload budget exhausted", privacy: .public)
            """
        )
        guard reload else {
            webView.loadHTMLString(
                DocumentKGPaneRoute.loadFailureHTML(
                    detail: "The reader's rendering process keeps terminating."
                ),
                baseURL: nil
            )
            return
        }
        lastLoadedDocumentId = nil
        lastLoadedLibraryPath = nil
        loadIfNeeded(webView)
    }
}
#endif
