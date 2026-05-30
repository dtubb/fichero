import FicheroAPIClient
import Foundation
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

    /// CSS that overrides the template's `:root` palette with the live macOS
    /// system colors (background, text, separators, accent) resolved for the
    /// current appearance. The template ships sensible light/dark defaults so
    /// it still looks right opened in a browser; in the app this makes the
    /// pane match the system exactly — accent included — and follow dark mode.
    /// Theming lives here (Swift) by design: the backend never sniffs the OS.
    @MainActor
    static func systemThemeCSS() -> String {
        func cssColor(_ color: NSColor) -> String {
            let resolved = color.usingColorSpace(.sRGB) ?? NSColor.black
            let red = Int((resolved.redComponent * 255).rounded())
            let green = Int((resolved.greenComponent * 255).rounded())
            let blue = Int((resolved.blueComponent * 255).rounded())
            return String(format: "rgba(%d, %d, %d, %.3f)", red, green, blue, resolved.alphaComponent)
        }

        var vars = ""
        NSApp.effectiveAppearance.performAsCurrentDrawingAppearance {
            vars = """
            --bg: \(cssColor(.textBackgroundColor));
            --panel: \(cssColor(.controlBackgroundColor));
            --text: \(cssColor(.textColor));
            --muted: \(cssColor(.secondaryLabelColor));
            --line: \(cssColor(.separatorColor));
            --accent: \(cssColor(.controlAccentColor));
            --accent-soft: \(cssColor(.controlAccentColor.withAlphaComponent(0.14)));
            """
        }
        return ":root{\(vars)}"
    }

    /// JS that injects (or refreshes) the system-theme `<style>` element so it
    /// overrides the template defaults regardless of load timing.
    @MainActor
    static func themeInjectionScript() -> String {
        let css = jsStringLiteral(systemThemeCSS())
        return """
        (function() {
            var id = 'fichero-system-theme';
            var el = document.getElementById(id);
            if (!el) {
                el = document.createElement('style');
                el.id = id;
                (document.head || document.documentElement).appendChild(el);
            }
            el.textContent = '\(css)';
        })();
        """
    }

    static func scrollSyncScript(pageCount: Int?) -> String {
        let count = max(pageCount ?? 0, 0)
        return """
        (function() {
            window.ficheroPageCount = \(count);
            window.ficheroScrollSyncSuppress = false;
            window.ficheroScrollToPage = function(pageNumber, pageCount) {
                var count = pageCount || window.ficheroPageCount || 0;
                var page = Number(pageNumber);
                var scroller = document.querySelector('.content') || document.scrollingElement;
                if (!scroller || count <= 1 || !Number.isFinite(page)) { return; }
                var maxScroll = scroller.scrollHeight - scroller.clientHeight;
                if (maxScroll <= 0) { return; }
                var progress = Math.max(0, Math.min(1, (page - 1) / Math.max(count - 1, 1)));
                window.ficheroScrollSyncSuppress = true;
                scroller.scrollTop = progress * maxScroll;
                window.setTimeout(function() { window.ficheroScrollSyncSuppress = false; }, 180);
            };
            if (window.ficheroScrollSyncInstalled) { return; }
            window.ficheroScrollSyncInstalled = true;
            var lastPage = null;
            var timer = null;
            function notifyPageFromScroll() {
                var count = window.ficheroPageCount || 0;
                var scroller = document.querySelector('.content') || document.scrollingElement;
                var handler = window.webkit?.messageHandlers?.ficheroBridge;
                if (!scroller || !handler || count <= 1 || window.ficheroScrollSyncSuppress) { return; }
                var maxScroll = scroller.scrollHeight - scroller.clientHeight;
                if (maxScroll <= 0) { return; }
                var progress = Math.max(0, Math.min(1, scroller.scrollTop / maxScroll));
                var page = Math.max(1, Math.min(count, Math.round(progress * (count - 1)) + 1));
                if (page === lastPage) { return; }
                lastPage = page;
                handler.postMessage({ kind: 'pageSelected', pageNumber: page });
            }
            function scheduleNotify() {
                window.clearTimeout(timer);
                timer = window.setTimeout(notifyPageFromScroll, 90);
            }
            var scroller = document.querySelector('.content') || document.scrollingElement;
            if (scroller) {
                scroller.addEventListener('scroll', scheduleNotify, { passive: true });
            }
        })();
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
    var selectedEntityId: String?
    var selectedClaimId: String?
    /// The tab the native toolbar (DocumentKGSurface) currently shows. Driving
    /// the tab from Swift — rather than the in-page HTML tab bar — keeps the
    /// switcher as fixed, never-scrolling AppKit chrome (#1228 follow-up).
    var activeTab: String = KGSurfaceTab.transcript.rawValue
    var activePageNumber: Int?
    var pageCount: Int?
    var onPageSelected: (Int) -> Void = { _ in }
    @Environment(KGFocusState.self) private var kgFocusState

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
        // Inject live macOS system colors at document end so they override the
        // template's default :root palette (same specificity, later wins).
        controller.addUserScript(
            WKUserScript(
                source: DocumentKGPaneRoute.themeInjectionScript(),
                injectionTime: .atDocumentEnd,
                forMainFrameOnly: true
            )
        )
        controller.addUserScript(
            WKUserScript(
                source: DocumentKGPaneRoute.scrollSyncScript(pageCount: pageCount),
                injectionTime: .atDocumentEnd,
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
        private var lastSelectedEntityId: String?
        private var lastSelectedClaimId: String?
        private var lastActivePageNumber: Int?
        private var lastActiveTab: String?
        private var suppressActivePageSyncUntil = Date.distantPast

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
            // A fresh document means a fresh DOM — clear the sync trackers so
            // didFinish re-applies the active tab + selection to the new page.
            lastActiveTab = nil
            lastSelectedEntityId = nil
            lastSelectedClaimId = nil
            lastActivePageNumber = nil
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
            if lastActiveTab != parent.activeTab {
                lastActiveTab = parent.activeTab
                let literal = DocumentKGPaneRoute.jsStringLiteral(parent.activeTab)
                webView.evaluateJavaScript("window.fichero?.showTab('\(literal)');")
            }

            if lastSelectedClaimId != parent.selectedClaimId {
                lastSelectedClaimId = parent.selectedClaimId
                if let claimId = parent.selectedClaimId {
                    let literal = DocumentKGPaneRoute.jsStringLiteral(claimId)
                    webView.evaluateJavaScript("window.fichero?.highlightClaim('\(literal)');")
                }
            }

            if lastSelectedEntityId != parent.selectedEntityId {
                lastSelectedEntityId = parent.selectedEntityId
                if let entityId = parent.selectedEntityId {
                    let literal = DocumentKGPaneRoute.jsStringLiteral(entityId)
                    webView.evaluateJavaScript("window.fichero?.highlightEntity?.('\(literal)');")
                }
            }

            if lastActivePageNumber != parent.activePageNumber {
                lastActivePageNumber = parent.activePageNumber
                if Date() < suppressActivePageSyncUntil {
                    return
                }
                if let pageNumber = parent.activePageNumber {
                    webView.evaluateJavaScript("window.fichero?.setActivePage(\(pageNumber));")
                    if let pageCount = parent.pageCount {
                        webView.evaluateJavaScript("window.ficheroScrollToPage?.(\(pageNumber), \(pageCount));")
                    }
                }
            }
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            injectContext(into: webView)
            webView.evaluateJavaScript(DocumentKGPaneRoute.themeInjectionScript())
            webView.evaluateJavaScript(DocumentKGPaneRoute.scrollSyncScript(pageCount: parent.pageCount))
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
                focusKGSource(
                    documentId: body["sourceDocumentId"] as? String,
                    entityId: entityId,
                    claimId: body["claimId"] as? String,
                    body: body
                )
            case "claimSelected":
                guard let claimId = body["claimId"] as? String else { return }
                focusKGSource(
                    documentId: body["sourceDocumentId"] as? String,
                    entityId: body["entityId"] as? String,
                    claimId: claimId,
                    body: body
                )
            case "pageSelected":
                guard let pageNumber = pageNumber(from: body) else { return }
                if parent.activePageNumber != pageNumber {
                    suppressActivePageSyncUntil = Date().addingTimeInterval(0.25)
                }
                parent.onPageSelected(max(0, pageNumber - 1))
            default:
                break
            }
        }

        private func focusKGSource(
            documentId: String?,
            entityId: String?,
            claimId: String?,
            body: [String: Any]
        ) {
            let sourceDocumentId = documentId ?? parent.documentId
            let pageLabel = pageLabel(from: body)
            postOpenClaimSource(sourceDocumentId: sourceDocumentId, pageLabel: pageLabel, entityId: entityId, claimId: claimId, body: body)
            Task { @MainActor in
                if let claimId, !claimId.isEmpty {
                    parent.kgFocusState.focusClaim(
                        claimId: claimId,
                        entityId: entityId,
                        sourceDocumentId: sourceDocumentId,
                        sourcePageLabel: pageLabel
                    )
                } else {
                    parent.kgFocusState.focusEntity(
                        entityId: entityId,
                        sourceDocumentId: sourceDocumentId,
                        sourcePageLabel: pageLabel
                    )
                }
            }
        }

        private func postOpenClaimSource(
            sourceDocumentId: String, pageLabel: String?, entityId: String?, claimId: String?, body: [String: Any]
        ) {
            guard var info = ClaimSummaryCard.openClaimSourceUserInfo(
                documentId: sourceDocumentId,
                pageLabel: pageLabel,
                charStart: body["charStart"] as? Int,
                charEnd: body["charEnd"] as? Int,
                claimId: claimId,
                excerpt: body["excerpt"] as? String
            ) else { return }
            if let entityId, !entityId.isEmpty {
                info["entityId"] = entityId
            }
            NotificationCenter.default.post(name: .ficheroOpenClaimSource, object: nil, userInfo: info)
        }

        private func pageLabel(from body: [String: Any]) -> String? {
            if let pageLabel = body["pageLabel"] as? String,
               !pageLabel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return pageLabel
            }
            if let sourcePageLabel = body["sourcePageLabel"] as? String,
               !sourcePageLabel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                return sourcePageLabel
            }
            if let pageNumber = body["pageNumber"] as? Int {
                return String(pageNumber)
            }
            if let pageNumber = body["pageNumber"] as? Double {
                return String(Int(pageNumber))
            }
            if let pageNumber = body["pageNumber"] as? NSNumber {
                return String(pageNumber.intValue)
            }
            return nil
        }

        private func pageNumber(from body: [String: Any]) -> Int? {
            if let pageNumber = body["pageNumber"] as? Int {
                return pageNumber
            }
            if let pageNumber = body["pageNumber"] as? Double {
                return Int(pageNumber)
            }
            if let pageNumber = body["pageNumber"] as? NSNumber {
                return pageNumber.intValue
            }
            return nil
        }
    }
}
