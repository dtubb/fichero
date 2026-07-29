import FicheroAPIClient
import Foundation
import SwiftUI
import WebKit

enum DocumentKGPaneRoute {
    // Members are in extensions: +Route, +Theme, +Scripts
}

#if canImport(AppKit)
import AppKit

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
    /// Reader text font scale (#3681). Bound to the shared key so a change
    /// re-invokes `updateNSView`, which re-injects the scaled `--reader-base-size`
    /// live — no reload (systemThemeCSS reads the current scale).
    @AppStorage(ViewSettings.FontScale.readerKey)
    var readerFontScale = ViewSettings.FontScale.defaultValue
    /// Reader paragraph wrapping (#3684). Also re-injected on change.
    @AppStorage(ReaderTextWrap.storageKey)
    var readerTextWrap = ReaderTextWrap.tidy
    @Environment(KGFocusState.self) var kgFocusState
    @Environment(LibraryManager.self) var libraryManager
    /// Per-window source-navigation bus (#3437). Captured into the coordinator
    /// in `updateNSView` — a WKScriptMessageHandler callback fires async, outside
    /// view evaluation, where reading `@Environment` directly is unsafe.
    @Environment(ClaimSourceNavigationState.self) var claimSourceNavigationState: ClaimSourceNavigationState?

    typealias Coordinator = DocumentKGWebPaneCoordinatorMacOS

    func makeCoordinator() -> Coordinator {
        Coordinator(parent: self)
    }

    func makeNSView(context: Context) -> GuardedWKWebView {
        let config = WKWebViewConfiguration()
        // The whole KG page loads over the custom `fichero-server://` origin so
        // `EngineWebViewSchemeHandler` funnels every navigation + relative
        // subresource through the transport-agnostic `FicheroClient` — making the
        // pane work over `.uds`/in-memory, not just HTTPS (a raw `https://…:8765`
        // navigation fails `-1004` when WKWebView can't dial the socket).
        if let client = DocumentKGPaneRoute.webViewClient(libraryPath: libraryPath, libraryManager: libraryManager) {
            config.setURLSchemeHandler(EngineWebViewSchemeHandler(client: client), forURLScheme: EngineWebViewURL.scheme)
        }
        // Storage images referenced as `fichero-res://…` inside KG HTML resolve
        // through the generated client too (transport-agnostic).
        config.setURLSchemeHandler(StorageResourceSchemeHandler(), forURLScheme: StorageResourceURL.scheme)
        let controller = config.userContentController
        controller.add(context.coordinator, name: "ficheroBridge")
        controller.addUserScript(
            WKUserScript(
                source: context.coordinator.bootstrapScript(forceRefresh: true),
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
        context.coordinator.claimSourceNavigationState = claimSourceNavigationState
        context.coordinator.injectContext(into: webView)
        context.coordinator.loadIfNeeded(webView)
        context.coordinator.syncSelection(into: webView)
        // Apply programmatic zoom from toolbar controls.
        if webView.pageZoom != zoom {
            webView.pageZoom = zoom
        }
        // Reader font-scale / wrap change (#3681 / #3684): re-inject the theme
        // (scaled --reader-base-size + --reader-text-wrap) in place. NaN/"" seeds
        // make the first pass a re-inject matching the on-load injection; later
        // changes update without a reload.
        if readerFontScale != context.coordinator.lastReaderFontScale
            || readerTextWrap.rawValue != context.coordinator.lastReaderTextWrap {
            context.coordinator.lastReaderFontScale = readerFontScale
            context.coordinator.lastReaderTextWrap = readerTextWrap.rawValue
            webView.evaluateJavaScript(DocumentKGPaneRoute.themeInjectionScript())
        }
    }
}
#elseif canImport(UIKit)
import UIKit

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
    /// Reader text font scale (#3681) — see the macOS pane. Re-injects the scaled
    /// `--reader-base-size` live on change.
    @AppStorage(ViewSettings.FontScale.readerKey)
    var readerFontScale = ViewSettings.FontScale.defaultValue
    /// Reader paragraph wrapping (#3684). Also re-injected on change.
    @AppStorage(ReaderTextWrap.storageKey)
    var readerTextWrap = ReaderTextWrap.tidy
    @Environment(KGFocusState.self) var kgFocusState
    @Environment(LibraryManager.self) var libraryManager
    /// Per-window source-navigation bus (#3437); captured into the coordinator
    /// in `updateUIView` for the async bridge callback.
    @Environment(ClaimSourceNavigationState.self) var claimSourceNavigationState: ClaimSourceNavigationState?

    typealias Coordinator = DocumentKGWebPaneCoordinatoriOS

    func makeCoordinator() -> Coordinator {
        Coordinator(parent: self)
    }

    func makeUIView(context: Context) -> GuardedWKWebView {
        let config = WKWebViewConfiguration()
        // See the macOS pane: the whole KG page loads over `fichero-server://` so
        // `EngineWebViewSchemeHandler` routes it through the transport-agnostic
        // `FicheroClient`, and `fichero-res://` storage assets resolve the same way.
        if let client = DocumentKGPaneRoute.webViewClient(libraryPath: libraryPath, libraryManager: libraryManager) {
            config.setURLSchemeHandler(EngineWebViewSchemeHandler(client: client), forURLScheme: EngineWebViewURL.scheme)
        }
        config.setURLSchemeHandler(StorageResourceSchemeHandler(), forURLScheme: StorageResourceURL.scheme)
        let controller = config.userContentController
        controller.add(context.coordinator, name: "ficheroBridge")
        controller.addUserScript(
            WKUserScript(
                source: context.coordinator.bootstrapScript(forceRefresh: true),
                injectionTime: .atDocumentStart,
                forMainFrameOnly: true
            )
        )
        // Live semantic theme on iOS too (#3683): inject the system colors/fonts/
        // base size at document end so the reader matches the app in light + dark.
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
        context.coordinator.claimSourceNavigationState = claimSourceNavigationState
        context.coordinator.injectContext(into: webView)
        context.coordinator.loadIfNeeded(webView)
        context.coordinator.syncSelection(into: webView)
        context.coordinator.applyZoom(to: webView, zoom: zoom)
        // Reader font-scale / wrap change (#3681 / #3684): re-inject in place.
        if readerFontScale != context.coordinator.lastReaderFontScale
            || readerTextWrap.rawValue != context.coordinator.lastReaderTextWrap {
            context.coordinator.lastReaderFontScale = readerFontScale
            context.coordinator.lastReaderTextWrap = readerTextWrap.rawValue
            webView.evaluateJavaScript(DocumentKGPaneRoute.themeInjectionScript())
        }
    }
}

#endif
