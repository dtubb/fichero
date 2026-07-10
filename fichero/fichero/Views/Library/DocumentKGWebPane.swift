// swiftlint:disable file_length
#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif
import FicheroAPIClient
import Foundation
import SwiftUI
import WebKit

enum DocumentKGPaneRoute {
    static let globalKGDocumentID = "__kg_global__"

    private static var baseURL: String {
        EngineConfig.host.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
    }

    static func documentURL(documentId: String) -> URL? {
        guard let encoded = documentId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) else {
            return nil
        }
        return URL(string: "\(baseURL)/view/document/\(encoded)")
    }

    static func supportsAuthenticatedWebView() -> Bool {
        let host = EngineConfig.host
        // Plain trust (loopback HTTP, or a CA-valid host): WKWebView's default
        // trust evaluation handles the connection, so the pane can load.
        if !RemoteCertificatePinning.shouldEnforcePinning(for: host) {
            return true
        }
        // Pinning is enforced (post-#2538 the loopback engine serves a
        // self-signed pinned HTTPS cert). The pane's WKNavigationDelegate now
        // validates the server trust against the persisted SPKI pin — the same
        // pinning the URLSession transport uses — so it can load as long as we
        // actually hold a pin for this host. Without a pin there is nothing to
        // validate against, so fall back to the unavailable placeholder.
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
        var request = URLRequest(url: url)
        request.addEngineAuth(libraryPath: libraryPath)
        return request
    }

    static func unavailableHTML() -> String {
        """
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <style>
            body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; background: #f6f6f6; color: #222; }
            main { max-width: 34rem; margin: 0 auto; padding: 2rem 1.25rem; }
            h1 { font-size: 1.1rem; margin: 0 0 0.75rem; }
            p { line-height: 1.45; color: #555; margin: 0.5rem 0; }
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
        window.ficheroToken = '\(tokenLiteral)';
        window.ficheroLibrary = '\(libraryLiteral)';
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

    #if canImport(AppKit)
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
        var selectionBg = ""
        var selectionText = ""
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
            // Bridge the macOS system selection color so ::selection in the
            // WebKit document matches the user's accent / appearance setting
            // instead of the browser's reddish-brown default (#1481).
            selectionBg = cssColor(.selectedTextBackgroundColor)
            selectionText = cssColor(.selectedTextColor)
        }
        return """
        :root{\(vars)}html,body{background:transparent!important;}
        ::selection{background-color:\(selectionBg);color:\(selectionText);}
        """
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
    #else
    @MainActor
    static func systemThemeCSS() -> String { "" }

    @MainActor
    static func themeInjectionScript() -> String { "" }
    #endif

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

#if canImport(AppKit)

/// A `WKWebView` that refuses to be sized with a non-finite or negative frame.
///
/// SwiftUI hosts this pane inside a `ZStack` that keeps it alive (at
/// `.opacity(0)`) across tab switches, and AppKit can transiently hand the view
/// a `NaN`/negative/zero size during layout. Passing such a size through to the
/// WebContent helper triggers WebKit's "Invalid frame dimension (negative or
/// non-finite)" warning and can crash/wedge the WebContent process so the
/// reading surface renders nothing (#1641). Clamping every incoming size to a
/// finite, non-negative value keeps WebContent alive without changing layout.
final class GuardedWKWebView: WKWebView {
    override func setFrameSize(_ newSize: NSSize) {
        let width = (newSize.width.isFinite && newSize.width > 0) ? newSize.width : 0
        let height = (newSize.height.isFinite && newSize.height > 0) ? newSize.height : 0
        super.setFrameSize(NSSize(width: width, height: height))
    }
}

// swiftlint:disable:next type_body_length
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
    var scrollSync: DocumentScrollSyncState
    /// Zoom level applied via WKWebView.pageZoom. 1.0 = 100%. (#2316)
    var zoom: Double = 1.0
    @Environment(KGFocusState.self) private var kgFocusState

    func makeCoordinator() -> Coordinator {
        Coordinator(parent: self)
    }

    func makeNSView(context: Context) -> GuardedWKWebView {
        let config = WKWebViewConfiguration()
        let controller = config.userContentController
        controller.add(context.coordinator, name: "ficheroBridge")
        if DocumentKGPaneRoute.supportsAuthenticatedWebView() {
            controller.addUserScript(
                WKUserScript(
                    source: context.coordinator.bootstrapScript(forceRefresh: true),
                    injectionTime: .atDocumentStart,
                    forMainFrameOnly: true
                )
            )
        }
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

        let webView = GuardedWKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        webView.underPageBackgroundColor = .clear
        // Enable trackpad pinch-to-zoom (#2316).
        webView.allowsMagnification = true
        context.coordinator.webView = webView
        context.coordinator.loadIfNeeded(webView)
        return webView
    }

    func updateNSView(_ webView: GuardedWKWebView, context: Context) {
        context.coordinator.parent = self
        context.coordinator.injectContext(into: webView)
        context.coordinator.loadIfNeeded(webView)
        context.coordinator.syncSelection(into: webView)
        // Apply programmatic zoom from toolbar controls.
        if webView.pageZoom != zoom {
            webView.pageZoom = zoom
        }
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        var parent: DocumentKGWebPane
        /// Retained weakly so the Coordinator can apply zoom without a full updateNSView cycle.
        weak var webView: GuardedWKWebView?

        private var lastLoadedDocumentId: String?
        private var lastLoadedLibraryPath: String?
        private var lastSelectedEntityId: String?
        private var lastSelectedClaimId: String?
        private var lastSelectedClaimCharStart: Int?
        private var lastSelectedClaimCharEnd: Int?
        private var lastActivePageNumber: Int?
        private var lastActiveTab: String?
        private var suppressActivePageSyncUntil = Date.distantPast
        private var cachedBootstrapScript: String?
        private var cachedBootstrapLibraryPath: String?

        init(parent: DocumentKGWebPane) {
            self.parent = parent
        }

        func loadIfNeeded(_ webView: WKWebView) {
            guard lastLoadedDocumentId != parent.documentId || lastLoadedLibraryPath != parent.libraryPath else { return }

            lastLoadedDocumentId = parent.documentId
            lastLoadedLibraryPath = parent.libraryPath
            // A fresh document means a fresh DOM — clear the sync trackers so
            // didFinish re-applies the active tab + selection to the new page.
            lastActiveTab = nil
            lastSelectedEntityId = nil
            lastSelectedClaimId = nil
            lastSelectedClaimCharStart = nil
            lastSelectedClaimCharEnd = nil
            lastActivePageNumber = nil
            guard let request = DocumentKGPaneRoute.request(
                documentId: parent.documentId,
                libraryPath: parent.libraryPath
            ) else {
                webView.loadHTMLString(DocumentKGPaneRoute.unavailableHTML(), baseURL: nil)
                return
            }
            webView.load(request)
        }

        func injectContext(into webView: WKWebView) {
            guard DocumentKGPaneRoute.supportsAuthenticatedWebView() else { return }
            webView.evaluateJavaScript(bootstrapScript())
        }

        func bootstrapScript(forceRefresh: Bool = false) -> String {
            if DocumentKGPaneRoute.shouldRefreshBootstrapScript(
                hasCachedScript: cachedBootstrapScript != nil,
                cachedLibraryPath: cachedBootstrapLibraryPath,
                libraryPath: parent.libraryPath,
                force: forceRefresh
            ) {
                cachedBootstrapLibraryPath = parent.libraryPath
                cachedBootstrapScript = DocumentKGPaneRoute.bootstrapScript(
                    token: AuthTokenMiddleware.readTokenFromDisk(),
                    libraryPath: parent.libraryPath
                )
            }
            return cachedBootstrapScript ?? ""
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
                    syncClaimSpan(claimId: claimId, into: webView)
                } else {
                    lastSelectedClaimCharStart = nil
                    lastSelectedClaimCharEnd = nil
                }
            }

            if lastSelectedEntityId != parent.selectedEntityId {
                lastSelectedEntityId = parent.selectedEntityId
                if let entityId = parent.selectedEntityId {
                    let literal = DocumentKGPaneRoute.jsStringLiteral(entityId)
                    // highlightEntity is now always defined (not a no-op); drop optional chaining.
                    webView.evaluateJavaScript("window.fichero?.highlightEntity('\(literal)');")
                }
            }

            if lastActivePageNumber != parent.activePageNumber {
                lastActivePageNumber = parent.activePageNumber
                if Date() < suppressActivePageSyncUntil {
                    return
                }
                if parent.scrollSync.isDriving(.web) {
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

        /// Scroll the transcript to the char range carried by ClaimFocusState for
        /// the given claim ID when it differs from the last-synced range.
        private func syncClaimSpan(claimId: String, into webView: WKWebView) {
            let focusState = ClaimFocusState.shared
            guard focusState.selectedClaimId == claimId,
                  let charStart = focusState.selectedClaimCharStart,
                  let charEnd = focusState.selectedClaimCharEnd,
                  charStart != lastSelectedClaimCharStart || charEnd != lastSelectedClaimCharEnd
            else { return }
            lastSelectedClaimCharStart = charStart
            lastSelectedClaimCharEnd = charEnd
            webView.evaluateJavaScript("window.fichero?.scrollToSpan(null, \(charStart), \(charEnd));")
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            injectContext(into: webView)
            webView.evaluateJavaScript(DocumentKGPaneRoute.themeInjectionScript())
            webView.evaluateJavaScript(DocumentKGPaneRoute.scrollSyncScript(pageCount: parent.pageCount))
            syncSelection(into: webView)
        }

        /// Validate the engine's TLS certificate against Fichero's persisted
        /// SPKI pin — the same pinned transport the URLSession stack uses. Post
        /// -#2538 the loopback engine serves a self-signed pinned HTTPS cert;
        /// without this the WebContent default trust evaluation rejects it and
        /// the reading / KG pane loads nothing.
        @MainActor
        func webView(
            _ webView: WKWebView,
            didReceive challenge: URLAuthenticationChallenge,
            completionHandler: @escaping @MainActor @Sendable (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
        ) {
            let (disposition, credential) = RemoteCertificatePinning.resolveServerTrustChallenge(challenge)
            completionHandler(disposition, credential)
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
                Task { @MainActor in
                    parent.kgFocusState.focusEntity(entityId: entityId)
                }
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
                guard parent.scrollSync.beginDriving(.web) else { return }
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
#elseif canImport(UIKit)

/// iOS guarded `WKWebView` that clamps transient non-finite/negative frames.
final class GuardedWKWebView: WKWebView {
    override func layoutSubviews() {
        let width = (bounds.width.isFinite && bounds.width > 0) ? bounds.width : 0
        let height = (bounds.height.isFinite && bounds.height > 0) ? bounds.height : 0
        if width != bounds.width || height != bounds.height {
            bounds = CGRect(origin: bounds.origin, size: CGSize(width: width, height: height))
        }
        super.layoutSubviews()
    }
}

// swiftlint:disable:next type_body_length
struct DocumentKGWebPane: UIViewRepresentable {
    let documentId: String
    let libraryPath: String
    var selectedEntityId: String?
    var selectedClaimId: String?
    var activeTab: String = KGSurfaceTab.transcript.rawValue
    var activePageNumber: Int?
    var pageCount: Int?
    var onPageSelected: (Int) -> Void = { _ in }
    var scrollSync: DocumentScrollSyncState
    var zoom: Double = 1.0
    @Environment(KGFocusState.self) private var kgFocusState

    func makeCoordinator() -> Coordinator {
        Coordinator(parent: self)
    }

    func makeUIView(context: Context) -> GuardedWKWebView {
        let config = WKWebViewConfiguration()
        let controller = config.userContentController
        controller.add(context.coordinator, name: "ficheroBridge")
        if DocumentKGPaneRoute.supportsAuthenticatedWebView() {
            controller.addUserScript(
                WKUserScript(
                    source: context.coordinator.bootstrapScript(forceRefresh: true),
                    injectionTime: .atDocumentStart,
                    forMainFrameOnly: true
                )
            )
        }
        // No live system theme on iOS in this pass; the template defaults apply.
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

        let webView = GuardedWKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        // iOS WKWebView has no `drawsBackground` KVC key (macOS-only) — setting it
        // crashes with NSUnknownKeyException. `isOpaque = false` + clear background
        // is the iOS-correct way to make the web pane transparent.
        webView.isOpaque = false
        webView.backgroundColor = .clear
        webView.scrollView.backgroundColor = .clear
        webView.scrollView.isMultipleTouchEnabled = true
        context.coordinator.webView = webView
        context.coordinator.loadIfNeeded(webView)
        return webView
    }

    func updateUIView(_ webView: GuardedWKWebView, context: Context) {
        context.coordinator.parent = self
        context.coordinator.injectContext(into: webView)
        context.coordinator.loadIfNeeded(webView)
        context.coordinator.syncSelection(into: webView)
        context.coordinator.applyZoom(to: webView, zoom: zoom)
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        var parent: DocumentKGWebPane
        weak var webView: GuardedWKWebView?

        private var lastLoadedDocumentId: String?
        private var lastLoadedLibraryPath: String?
        private var lastSelectedEntityId: String?
        private var lastSelectedClaimId: String?
        private var lastSelectedClaimCharStart: Int?
        private var lastSelectedClaimCharEnd: Int?
        private var lastActivePageNumber: Int?
        private var lastActiveTab: String?
        private var suppressActivePageSyncUntil = Date.distantPast
        private var lastAppliedZoom: Double = 1.0
        private var cachedBootstrapScript: String?
        private var cachedBootstrapLibraryPath: String?

        init(parent: DocumentKGWebPane) {
            self.parent = parent
        }

        func loadIfNeeded(_ webView: WKWebView) {
            guard lastLoadedDocumentId != parent.documentId || lastLoadedLibraryPath != parent.libraryPath else { return }

            lastLoadedDocumentId = parent.documentId
            lastLoadedLibraryPath = parent.libraryPath
            lastAppliedZoom = 0  // Force viewport injection on next load even when zoom == 1.0
            lastActiveTab = nil
            lastSelectedEntityId = nil
            lastSelectedClaimId = nil
            lastSelectedClaimCharStart = nil
            lastSelectedClaimCharEnd = nil
            lastActivePageNumber = nil
            guard let request = DocumentKGPaneRoute.request(
                documentId: parent.documentId,
                libraryPath: parent.libraryPath
            ) else {
                webView.loadHTMLString(DocumentKGPaneRoute.unavailableHTML(), baseURL: nil)
                return
            }
            webView.load(request)
        }

        func injectContext(into webView: WKWebView) {
            guard DocumentKGPaneRoute.supportsAuthenticatedWebView() else { return }
            webView.evaluateJavaScript(bootstrapScript())
        }

        func bootstrapScript(forceRefresh: Bool = false) -> String {
            if DocumentKGPaneRoute.shouldRefreshBootstrapScript(
                hasCachedScript: cachedBootstrapScript != nil,
                cachedLibraryPath: cachedBootstrapLibraryPath,
                libraryPath: parent.libraryPath,
                force: forceRefresh
            ) {
                cachedBootstrapLibraryPath = parent.libraryPath
                cachedBootstrapScript = DocumentKGPaneRoute.bootstrapScript(
                    token: AuthTokenMiddleware.readTokenFromDisk(),
                    libraryPath: parent.libraryPath
                )
            }
            return cachedBootstrapScript ?? ""
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
                    syncClaimSpan(claimId: claimId, into: webView)
                } else {
                    lastSelectedClaimCharStart = nil
                    lastSelectedClaimCharEnd = nil
                }
            }

            if lastSelectedEntityId != parent.selectedEntityId {
                lastSelectedEntityId = parent.selectedEntityId
                if let entityId = parent.selectedEntityId {
                    let literal = DocumentKGPaneRoute.jsStringLiteral(entityId)
                    webView.evaluateJavaScript("window.fichero?.highlightEntity('\(literal)');")
                }
            }

            if lastActivePageNumber != parent.activePageNumber {
                lastActivePageNumber = parent.activePageNumber
                if Date() < suppressActivePageSyncUntil {
                    return
                }
                if parent.scrollSync.isDriving(.web) {
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

        private func syncClaimSpan(claimId: String, into webView: WKWebView) {
            let focusState = ClaimFocusState.shared
            guard focusState.selectedClaimId == claimId,
                  let charStart = focusState.selectedClaimCharStart,
                  let charEnd = focusState.selectedClaimCharEnd,
                  charStart != lastSelectedClaimCharStart || charEnd != lastSelectedClaimCharEnd
            else { return }
            lastSelectedClaimCharStart = charStart
            lastSelectedClaimCharEnd = charEnd
            webView.evaluateJavaScript("window.fichero?.scrollToSpan(null, \(charStart), \(charEnd));")
        }

        func applyZoom(to webView: WKWebView, zoom: Double) {
            guard zoom != lastAppliedZoom else { return }
            lastAppliedZoom = zoom
            let literal = DocumentKGPaneRoute.jsStringLiteral(String(format: "%.4f", zoom))
            webView.evaluateJavaScript("""
            (function() {
                var el = document.getElementById('fichero-viewport');
                if (!el) {
                    el = document.createElement('meta');
                    el.id = 'fichero-viewport';
                    el.name = 'viewport';
                    (document.head || document.documentElement).appendChild(el);
                }
                el.content = 'width=device-width, initial-scale=1.0, minimum-scale=0.5, maximum-scale=5.0, user-scalable=yes';
                document.body.style.zoom = '\(literal)';
            })();
            """)
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            injectContext(into: webView)
            webView.evaluateJavaScript(DocumentKGPaneRoute.themeInjectionScript())
            webView.evaluateJavaScript(DocumentKGPaneRoute.scrollSyncScript(pageCount: parent.pageCount))
            syncSelection(into: webView)
            applyZoom(to: webView, zoom: parent.zoom)
        }

        /// Validate the engine's TLS certificate against Fichero's persisted
        /// SPKI pin — the same pinned transport the URLSession stack uses (see
        /// the macOS variant for the rationale, #2538).
        @MainActor
        func webView(
            _ webView: WKWebView,
            didReceive challenge: URLAuthenticationChallenge,
            completionHandler: @escaping @MainActor @Sendable (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
        ) {
            let (disposition, credential) = RemoteCertificatePinning.resolveServerTrustChallenge(challenge)
            completionHandler(disposition, credential)
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
                Task { @MainActor in
                    parent.kgFocusState.focusEntity(entityId: entityId)
                }
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
                guard parent.scrollSync.beginDriving(.web) else { return }
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

#endif
