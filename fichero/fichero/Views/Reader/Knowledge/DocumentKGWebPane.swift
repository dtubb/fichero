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
    /// A trackpad pinch, as a magnification delta (#5203). WebKit's own `magnification` scales the page
    /// WITHOUT reflowing it, so a pinch pushed the text past the column and the pane scrolled sideways;
    /// the pinch goes to the host's zoom instead, which is `pageZoom` and reflows.
    var onPinch: ((CGFloat) -> Void)?

    override func setFrameSize(_ newSize: NSSize) {
        let width = (newSize.width.isFinite && newSize.width > 0) ? newSize.width : 0
        let height = (newSize.height.isFinite && newSize.height > 0) ? newSize.height : 0
        super.setFrameSize(NSSize(width: width, height: height))
    }

    override func magnify(with event: NSEvent) {
        guard let onPinch else { return super.magnify(with: event) }
        onPinch(event.magnification)
    }
}

/// The Reader's zoom (#5203): ONE value, `pageZoom`, which enlarges the text and reflows it to the column
/// (for vertical text, to the column's height). The toolbar, ⌘+ / ⌘− and a pinch all move it.
enum ReaderZoom {
    static let range: ClosedRange<Double> = 0.5...3.0

    /// A pinch's magnification delta applied to the zoom, kept in range.
    static func pinched(_ zoom: Double, by magnification: Double) -> Double {
        min(range.upperBound, max(range.lowerBound, zoom * (1 + magnification)))
    }
}

struct DocumentKGWebPane: NSViewRepresentable {
    let documentId: String
    let libraryPath: String
    /// Non-empty = render ONLY these child pages (the multi-page selection
    /// view, 2026-08-25). Rides `?pages=` on the same document route.
    var pageIds: [String] = []
    /// Non-nil = read the scope through THIS representation type (transcription,
    /// translation, …) instead of the live content (2026-08-29). Rides
    /// `?representation=` on the same document route.
    var representation: String?
    var selectedEntityId: String?
    var selectedClaimId: String?
    /// The tab the native toolbar (DocumentKGSurface) currently shows. Driving
    /// the tab from Swift — rather than the in-page HTML tab bar — keeps the
    /// switcher as fixed, never-scrolling AppKit chrome (#1228 follow-up).
    var activeTab: String = KGSurfaceTab.transcript.rawValue
    var activePageNumber: Int?
    /// The selected page's own node id, when the reader is focused on a page.
    /// Scrolls the transcript by id (`<article data-page-id>`) — robust where
    /// `activePageNumber` is not: manifest-imported image pages leave the
    /// top-level `sequence` null, so the ordinal path stranded every selected
    /// hit on the parent's first page (#reader-page-id).
    var activePageId: String?
    var pageCount: Int?
    var onPageSelected: (Int) -> Void = { _ in }
    var scrollSync: DocumentScrollSyncState
    /// Zoom level applied via WKWebView.pageZoom. 1.0 = 100%. (#2316)
    var zoom: Double = 1.0
    /// A pinch moved the zoom (#5203): the host sets `zoom`, so a pinch reflows as the toolbar does.
    var onPinchZoom: ((Double) -> Void)?
    /// In-reader find (#4338): the live query ("" = cleared), the 0-based
    /// current match to select, and the match-count report back to the bar.
    var searchQuery: String = ""
    var searchSelectionIndex: Int = -1
    var onSearchMatchCount: (@MainActor @Sendable (Int) -> Void)? = nil // swiftlint:disable:this implicit_optional_initialization
    /// Pages a running workflow is writing (#4357) — the run's target set via
    /// `DocumentStore.isDocumentBusy`, NOT a second notion of "working".
    var busyPageNumbers: Set<Int> = []
    /// Live `page number -> content` for those pages, patched into the reader in
    /// place so a mid-run write never reloads the WKWebView.
    var pageContentPatches: [Int: String] = [:]
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
    /// The window's focused Source-view selection, shown in the Reader and set from it (#5155).
    @Environment(WindowState.self) var windowState: WindowState?
    /// Per-window source-navigation bus (#3437). Captured into the coordinator
    /// in `updateNSView` — a WKScriptMessageHandler callback fires async, outside
    /// view evaluation, where reading `@Environment` directly is unsafe.
    @Environment(ClaimSourceNavigationState.self) var claimSourceNavigationState: ClaimSourceNavigationState?
    /// Per-window reader page-activation bus (#4373). Same capture-into-the-
    /// coordinator discipline as the line above, for the same reason.
    @Environment(ReaderPageActivationState.self) var readerPageActivationState: ReaderPageActivationState?

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
        // Pinch-to-zoom (#2316) goes to `pageZoom`, which reflows, never WebKit's magnification (#5203).
        webView.allowsMagnification = false
        // No focus ring (Daniel, 2026-09-01). Same stray blue line as the
        // transcript's scroll view: WebKit's own scroll view draws a ring when
        // the graph pane takes key focus, and it lands as a rule across the
        // top of the reader pane.
        webView.focusRingType = .none
        context.coordinator.webView = webView
        context.coordinator.loadIfNeeded(webView)
        return webView
    }

    /// The window closes or the pane goes: the page sends the line being typed (#5001). Best effort --
    /// a torn-down web view may not run it; the page also commits on focus leaving it.
    static func dismantleNSView(_ webView: GuardedWKWebView, coordinator: Coordinator) {
        webView.evaluateJavaScript(ReaderTextEdit.commitPendingScript)
    }

    func updateNSView(_ webView: GuardedWKWebView, context: Context) {
        context.coordinator.parent = self
        context.coordinator.claimSourceNavigationState = claimSourceNavigationState
        context.coordinator.readerPageActivationState = readerPageActivationState
        context.coordinator.library = libraryManager.library(atPath: libraryPath)
        context.coordinator.windowState = windowState
        context.coordinator.syncSelectedLines(into: webView)
        context.coordinator.syncRegionRules(into: webView)
        context.coordinator.injectContext(into: webView)
        context.coordinator.loadIfNeeded(webView)
        context.coordinator.syncSelection(into: webView)
        // A pinch moves the host's zoom, from the zoom shown now.
        let zoom = zoom
        webView.onPinch = onPinchZoom.map { report in { magnification in report(ReaderZoom.pinched(zoom, by: magnification)) } }
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
    /// Non-empty = render ONLY these child pages (see the macOS twin above).
    var pageIds: [String] = []
    /// Non-nil = read the scope through THIS representation type (see the
    /// macOS twin above).
    var representation: String?
    var selectedEntityId: String?
    var selectedClaimId: String?
    var activeTab: String = KGSurfaceTab.transcript.rawValue
    var activePageNumber: Int?
    /// The selected page's own node id — see the macOS twin above. Scrolls the
    /// transcript by `<article data-page-id>`, robust where the ordinal
    /// `activePageNumber` is null (#reader-page-id).
    var activePageId: String?
    var pageCount: Int?
    var onPageSelected: (Int) -> Void = { _ in }
    var scrollSync: DocumentScrollSyncState
    var zoom: Double = 1.0
    /// A pinch moved the zoom (#5203) -- see the macOS pane; iOS pinches the web view's own scroll view.
    var onPinchZoom: ((Double) -> Void)?
    /// In-reader find (#4338) — see the macOS pane.
    var searchQuery: String = ""
    var searchSelectionIndex: Int = -1
    var onSearchMatchCount: (@MainActor @Sendable (Int) -> Void)? = nil // swiftlint:disable:this implicit_optional_initialization
    /// Per-page run progress + live page writes (#4357) — see the macOS pane.
    var busyPageNumbers: Set<Int> = []
    var pageContentPatches: [Int: String] = [:]
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
    /// Per-window reader page-activation bus (#4373). Same capture-into-the-
    /// coordinator discipline as the line above, for the same reason.
    @Environment(ReaderPageActivationState.self) var readerPageActivationState: ReaderPageActivationState?

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
        context.coordinator.readerPageActivationState = readerPageActivationState
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
