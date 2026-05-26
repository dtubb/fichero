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
    /// The tab the native toolbar (DocumentKGSurface) currently shows. Driving
    /// the tab from Swift — rather than the in-page HTML tab bar — keeps the
    /// switcher as fixed, never-scrolling AppKit chrome (#1228 follow-up).
    var activeTab: String = KGSurfaceTab.transcript.rawValue
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
        // Inject live macOS system colors at document end so they override the
        // template's default :root palette (same specificity, later wins).
        controller.addUserScript(
            WKUserScript(
                source: DocumentKGPaneRoute.themeInjectionScript(),
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
        private var lastSelectedClaimId: String?
        private var lastActivePageNumber: Int?
        private var lastActiveTab: String?

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

            if lastActivePageNumber != parent.activePageNumber {
                lastActivePageNumber = parent.activePageNumber
                if let pageNumber = parent.activePageNumber {
                    webView.evaluateJavaScript("window.fichero?.setActivePage(\(pageNumber));")
                }
            }
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            injectContext(into: webView)
            webView.evaluateJavaScript(DocumentKGPaneRoute.themeInjectionScript())
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

// MARK: - Knowledge Surface Tabs (#1228 follow-up)

/// The three views the knowledge surface can show. `rawValue` matches the
/// tab ids the in-page JS (`document_view.html`) expects, so the native
/// toolbar and the web content stay in lock-step through `fichero.showTab`.
enum KGSurfaceTab: String, CaseIterable, Identifiable {
    case transcript
    case digest
    case graph

    var id: String { rawValue }

    /// Human-readable label shown on the native toolbar button.
    var title: String {
        switch self {
        case .transcript: return "Transcript"
        case .digest: return "Digest"
        case .graph: return "Graph"
        }
    }

    /// SF Symbol mirroring the inspector tab-bar visual language.
    var icon: String {
        switch self {
        case .transcript: return "doc.text"
        case .digest: return "list.bullet.rectangle"
        case .graph: return "point.3.connected.trianglepath.dotted"
        }
    }
}

/// Hosts `DocumentKGWebPane` beneath a fixed, never-scrolling native tab
/// strip. The web view only ever renders content — the Transcript/Digest/Graph
/// switcher is AppKit chrome (`MiniToolbar`, 44pt) styled like the library
/// mode rail and inspector tabs, so it can't scroll out of view and matches
/// the rest of the window's pane headers. (#1228)
struct DocumentKGSurface: View {
    let documentId: String
    let libraryPath: String
    var selectedClaimId: String?
    var activePageNumber: Int?
    var onEntitySelected: (String, String?) -> Void = { _, _ in }
    var onClaimSelected: (String, String?, String?) -> Void = { _, _, _ in }

    @State private var activeTab: KGSurfaceTab = .transcript

    var body: some View {
        VStack(spacing: 0) {
            // Same button style as the DocumentInspector tab bar (full-height
            // hit area, centered icon, rounded-rect selection highlight),
            // centered as a group. Unifies the knowledge-surface header with
            // the inspector tabs + library mode rail. (#1228)
            MiniToolbar {
                Spacer(minLength: 0)
                ForEach(KGSurfaceTab.allCases) { tab in
                    tabButton(tab)
                }
                Spacer(minLength: 0)
            }

            Divider()

            DocumentKGWebPane(
                documentId: documentId,
                libraryPath: libraryPath,
                selectedClaimId: selectedClaimId,
                activeTab: activeTab.rawValue,
                activePageNumber: activePageNumber,
                onEntitySelected: onEntitySelected,
                onClaimSelected: onClaimSelected
            )
        }
    }

    /// One knowledge-surface tab button, styled like the DocumentInspector tab
    /// bar. Extracted from the toolbar's ForEach so the inline body stays under
    /// the SwiftUI type-checker's complexity limit.
    @ViewBuilder
    private func tabButton(_ tab: KGSurfaceTab) -> some View {
        let isSelected = activeTab == tab
        Button {
            activeTab = tab
        } label: {
            Image(systemName: tab.icon)
                .font(.system(size: 16, weight: .regular))
                .frame(width: 40)
                .frame(maxHeight: .infinity)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .background(
            RoundedRectangle(cornerRadius: 6)
                .fill(isSelected ? Color.accentColor.opacity(0.15) : Color.clear)
        )
        .foregroundStyle(isSelected ? Color.accentColor : Color.secondary)
        .help(tab.title)
    }
}
