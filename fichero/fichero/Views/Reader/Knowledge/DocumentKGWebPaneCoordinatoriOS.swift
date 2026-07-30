#if canImport(UIKit)
import FicheroAPIClient
import Foundation
import OSLog
import UIKit
import WebKit

final class DocumentKGWebPaneCoordinatoriOS: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
    var parent: DocumentKGWebPane?
    /// Last Reader font scale re-injected (#3681); NaN so the first compare fires.
    var lastReaderFontScale: Double = .nan
    /// Last Reader wrap mode re-injected (#3684); "" so the first compare fires.
    var lastReaderTextWrap: String = ""
    /// Per-window source-navigation bus, captured each `updateUIView` (#3437).
    var claimSourceNavigationState: ClaimSourceNavigationState?
    /// Per-window reader page-activation bus (#4373), captured the same way and
    /// for the same reason: a click on a page arrives on an async bridge
    /// callback, outside view evaluation, where reading `@Environment` is unsafe.
    var readerPageActivationState: ReaderPageActivationState?
    weak var webView: GuardedWKWebView?

    var lastLoadedDocumentId: String?
    var lastLoadedLibraryPath: String?
    var lastSelectedEntityId: String?
    var lastSelectedClaimId: String?
    var lastSelectedClaimCharStart: Int?
    var lastSelectedClaimCharEnd: Int?
    var lastActivePageNumber: Int?
    var lastActiveTab: String?
    var suppressActivePageSyncUntil = Date.distantPast
    private var lastAppliedZoom: Double = 1.0
    var cachedBootstrapScript: String?
    var cachedBootstrapLibraryPath: String?
    /// In-reader find sync (#4338) — shared query/index dedupe.
    let findSync = WebPaneFindSync()
    /// Per-page run progress + live page writes (#4357) — see the macOS coordinator.
    let progressSync = WebPaneProgressSync()

    init(parent: DocumentKGWebPane) {
        self.parent = parent
    }

    func loadIfNeeded(_ webView: WKWebView) {
        guard lastLoadedDocumentId != parent?.documentId || lastLoadedLibraryPath != parent?.libraryPath else { return }

        lastLoadedDocumentId = parent?.documentId
        lastLoadedLibraryPath = parent?.libraryPath
        lastAppliedZoom = 0  // Force viewport injection on next load even when zoom == 1.0
        lastActiveTab = nil
        lastSelectedEntityId = nil
        lastSelectedClaimId = nil
        lastSelectedClaimCharStart = nil
        lastSelectedClaimCharEnd = nil
        lastActivePageNumber = nil
        findSync.reset()
        progressSync.reset()
        guard let parent, let request = DocumentKGPaneRoute.request(
            documentId: parent.documentId,
            libraryPath: parent.libraryPath
        ) else {
            // Only reachable when the document id can't form a URL — the
            // remote-host availability gate is retired (loads route through
            // FicheroClient, which applies auth + pinning itself).
            webView.loadHTMLString(
                DocumentKGPaneRoute.loadFailureHTML(detail: "The document's address could not be constructed."),
                baseURL: nil
            )
            return
        }
        webView.load(request)
    }

    func injectContext(into webView: WKWebView) {
        webView.evaluateJavaScript(bootstrapScript())
    }

    func bootstrapScript(forceRefresh: Bool = false) -> String {
        guard let parent else { return "" }
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
        guard let parent else { return }
        syncActiveTab(into: webView, activeTab: parent.activeTab)
        syncSelectedClaim(into: webView, selectedClaimId: parent.selectedClaimId)
        syncSelectedEntity(into: webView, selectedEntityId: parent.selectedEntityId)
        syncActivePage(into: webView, parent: parent)
        // In-reader find (#4338): query re-run + current-match select.
        findSync.sync(
            into: webView,
            query: parent.searchQuery,
            selectionIndex: parent.searchSelectionIndex,
            onMatchCount: parent.onSearchMatchCount
        )
        // Per-page run progress + live page writes (#4357).
        progressSync.sync(
            into: webView,
            busyPages: parent.busyPageNumbers,
            pageContent: parent.pageContentPatches
        )
    }

    func syncActiveTab(into webView: WKWebView, activeTab: String) {
        if lastActiveTab != activeTab {
            lastActiveTab = activeTab
            let literal = DocumentKGPaneRoute.jsStringLiteral(activeTab)
            webView.evaluateJavaScript("window.fichero?.showTab('\(literal)');")
        }
    }

    func syncSelectedClaim(into webView: WKWebView, selectedClaimId: String?) {
        if lastSelectedClaimId != selectedClaimId {
            lastSelectedClaimId = selectedClaimId
            if let claimId = selectedClaimId {
                let literal = DocumentKGPaneRoute.jsStringLiteral(claimId)
                webView.evaluateJavaScript("window.fichero?.highlightClaim('\(literal)');")
                syncClaimSpan(claimId: claimId, into: webView)
            } else {
                lastSelectedClaimCharStart = nil
                lastSelectedClaimCharEnd = nil
            }
        }
    }

    func syncSelectedEntity(into webView: WKWebView, selectedEntityId: String?) {
        if lastSelectedEntityId != selectedEntityId {
            lastSelectedEntityId = selectedEntityId
            if let entityId = selectedEntityId {
                let literal = DocumentKGPaneRoute.jsStringLiteral(entityId)
                webView.evaluateJavaScript("window.fichero?.highlightEntity('\(literal)');")
            }
        }
    }

    /// Move the transcript's own selected-page border to the page-focus cursor
    /// (#4373). The decision is pure and lives in `ReaderActivePageSync`; this
    /// only performs it.
    func syncActivePage(into webView: WKWebView, parent: DocumentKGWebPane) {
        let decision = ReaderActivePageSync.decide(
            lastSent: lastActivePageNumber,
            desired: parent.activePageNumber,
            isScrollSuppressed: Date() < suppressActivePageSyncUntil,
            isWebDriving: parent.scrollSync.isDriving(.web)
        )
        guard decision.sendsHighlight else { return }
        // Record ONLY what actually went out. The old code recorded before its
        // early returns, so a suppressed tick marked the border delivered and
        // left it on the wrong page (#4373).
        lastActivePageNumber = parent.activePageNumber
        webView.evaluateJavaScript(
            ReaderActivePageSync.highlightScript(page: parent.activePageNumber)
        )
        if decision.sendsScroll,
           let pageNumber = parent.activePageNumber,
           let pageCount = parent.pageCount {
            webView.evaluateJavaScript(
                ReaderActivePageSync.scrollScript(page: pageNumber, pageCount: pageCount)
            )
        }
    }

    func syncClaimSpan(claimId: String, into webView: WKWebView) {
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
        webView.evaluateJavaScript(DocumentKGPaneRoute.scrollSyncScript(pageCount: parent?.pageCount))
        // Fresh DOM: drop the progress dedupe so the spinner/live text re-apply.
        progressSync.reset()
        syncSelection(into: webView)
        applyZoom(to: webView, zoom: parent?.zoom ?? 1.0)
    }

    /// A genuine fetch failure (pinned remote unreachable, engine non-2xx) fails
    /// the `fichero-server://` provisional navigation. Fall back to the static
    /// failure page. Only fires for engine loads (or the key-less handler
    /// errors) so the `about:blank` failure page can't re-trigger a loop.
    func webView(
        _ webView: WKWebView,
        didFailProvisionalNavigation navigation: WKNavigation!,
        withError error: any Error
    ) {
        if error.isCancellationError { return }
        let failingURL = (error as NSError).userInfo[NSURLErrorFailingURLStringErrorKey] as? String
        guard failingURL == nil || failingURL?.hasPrefix(EngineWebViewURL.scheme) == true else { return }
        webView.loadHTMLString(
            DocumentKGPaneRoute.loadFailureHTML(detail: error.localizedDescription),
            baseURL: nil
        )
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
                parent?.kgFocusState.focusEntity(entityId: entityId)
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
            if parent?.activePageNumber != pageNumber {
                suppressActivePageSyncUntil = Date().addingTimeInterval(0.25)
            }
            guard parent?.scrollSync.beginDriving(.web) ?? false else { return }
            parent?.onPageSelected(max(0, pageNumber - 1))
        case "pageActivated":
            // A CLICK, not a scroll (#4373). It is allowed to move the library
            // selection and the preview, which `pageSelected` deliberately is
            // not (#1463) — hence the separate kind and the separate bus. No
            // scroll-sync driving claim: the user is not scrolling.
            handlePageActivated(body)
        default:
            break
        }
    }

}

// Bridge-message routing, in an extension so the coordinator's own body stays
// under the SwiftLint type-body threshold.
extension DocumentKGWebPaneCoordinatoriOS {
    /// A reader page click (#4373). Validates the bridge payload and publishes
    /// it on the per-window activation bus, where ContentView routes it through
    /// the SAME selection path a sidebar click uses — so the sidebar highlight,
    /// the preview and the inspector all follow as observers rather than
    /// through a parallel navigation of their own.
    ///
    /// A malformed or out-of-range page is REPORTED, never clamped: silently
    /// selecting page 1 because the payload said 0 is precisely the kind of
    /// quiet wrong answer that makes a navigation bug unfindable.
    func handlePageActivated(_ body: [String: Any]) {
        guard let pageNumber = pageNumber(from: body) else {
            readerPageActivationLogger.error("Reader page click carried no usable page number")
            return
        }
        // The click came from INSIDE the transcript, so the page is already on
        // screen. Suppress the follow-up scroll only — the border still moves,
        // because `ReaderActivePageSync` never suppresses the highlight (#4373).
        // Without this, clicking a visible page yanks it to the top of the
        // viewport and moves the text out from under the pointer.
        suppressActivePageSyncUntil = Date().addingTimeInterval(0.25)
        Task { @MainActor in
            guard let state = readerPageActivationState else { return }
            if !state.activate(pageNumber: pageNumber) {
                readerPageActivationLogger.error(
                    "Reader page click carried an out-of-range page number \(pageNumber, privacy: .public)"
                )
            }
        }
    }

    func focusKGSource(
        documentId: String?,
        entityId: String?,
        claimId: String?,
        body: [String: Any]
    ) {
        guard let parent else { return }
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

    func postOpenClaimSource(
        sourceDocumentId: String, pageLabel: String?, entityId: String?, claimId: String?, body: [String: Any]
    ) {
        guard let request = ClaimSummaryCard.openClaimSourceRequest(
            documentId: sourceDocumentId,
            pageLabel: pageLabel,
            charStart: body["charStart"] as? Int,
            charEnd: body["charEnd"] as? Int,
            claimId: claimId,
            excerpt: body["excerpt"] as? String
        ) else { return }
        _ = entityId
        claimSourceNavigationState?.request(request)
    }

    func pageLabel(from body: [String: Any]) -> String? {
        documentKGPageLabel(from: body)
    }

    func pageNumber(from body: [String: Any]) -> Int? {
        documentKGPageNumber(from: body)
    }
}

private func documentKGPageLabel(from body: [String: Any]) -> String? {
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

private func documentKGPageNumber(from body: [String: Any]) -> Int? {
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

#endif
