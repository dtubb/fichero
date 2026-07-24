#if canImport(AppKit)
import AppKit
import FicheroAPIClient
import Foundation
import WebKit

final class DocumentKGWebPaneCoordinatorMacOS: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
    var parent: DocumentKGWebPane?
    /// Last Reader font scale re-injected (#3681); NaN so the first compare fires.
    var lastReaderFontScale: Double = .nan
    /// Last Reader wrap mode re-injected (#3684); "" so the first compare fires.
    var lastReaderTextWrap: String = ""
    /// Per-window source-navigation bus, captured from the environment each
    /// `updateNSView` so async bridge callbacks route to THIS window (#3437).
    var claimSourceNavigationState: ClaimSourceNavigationState?
    /// Retained weakly so the Coordinator can apply zoom without a full updateNSView cycle.
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
    var cachedBootstrapScript: String?
    var cachedBootstrapLibraryPath: String?

    init(parent: DocumentKGWebPane) {
        self.parent = parent
    }

    func loadIfNeeded(_ webView: WKWebView) {
        guard lastLoadedDocumentId != parent?.documentId || lastLoadedLibraryPath != parent?.libraryPath else { return }

        lastLoadedDocumentId = parent?.documentId
        lastLoadedLibraryPath = parent?.libraryPath
        // A fresh document means a fresh DOM — clear the sync trackers so
        // didFinish re-applies the active tab + selection to the new page.
        lastActiveTab = nil
        lastSelectedEntityId = nil
        lastSelectedClaimId = nil
        lastSelectedClaimCharStart = nil
        lastSelectedClaimCharEnd = nil
        lastActivePageNumber = nil
        guard let parent, let request = DocumentKGPaneRoute.request(
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

    func syncActivePage(into webView: WKWebView, parent: DocumentKGWebPane) {
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

    /// A genuine fetch failure (e.g. a pinned remote host the client can't reach,
    /// or the engine returning non-2xx) fails the `fichero-engine://` provisional
    /// navigation. Fall back to the static "unavailable" page rather than leaving
    /// WebKit's default error surface. Only fires for `fichero-engine://` loads so
    /// the `about:blank` unavailable page itself can't re-trigger a loop.
    func webView(
        _ webView: WKWebView,
        didFailProvisionalNavigation navigation: WKNavigation!,
        withError error: any Error
    ) {
        loadUnavailableIfEngineLoad(webView, error: error)
    }

    private func loadUnavailableIfEngineLoad(_ webView: WKWebView, error: any Error) {
        if error.isCancellationError { return }
        // Scheme-handler failures lack a failing URL, while transport failures include one.
        // Limit fallback to engine-origin loads so the standalone unavailable page cannot loop.
        let failingURL = (error as NSError).userInfo[NSURLErrorFailingURLStringErrorKey] as? String
        guard failingURL == nil || failingURL?.hasPrefix(EngineWebViewURL.scheme) == true else { return }
        webView.loadHTMLString(DocumentKGPaneRoute.unavailableHTML(), baseURL: nil)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        injectContext(into: webView)
        webView.evaluateJavaScript(DocumentKGPaneRoute.themeInjectionScript())
        webView.evaluateJavaScript(DocumentKGPaneRoute.scrollSyncScript(pageCount: parent?.pageCount))
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
        default:
            break
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
        documentKGPageLabelMacOS(from: body)
    }

    func pageNumber(from body: [String: Any]) -> Int? {
        documentKGPageNumberMacOS(from: body)
    }
}

private func documentKGPageLabelMacOS(from body: [String: Any]) -> String? {
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

private func documentKGPageNumberMacOS(from body: [String: Any]) -> Int? {
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
