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

// swiftlint:disable:next type_body_length
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
            /* Semantic palette matching document_view.html so this fallback page
               reads as the same app in light AND dark (#3683), even though the
               theme-injection script doesn't run on this standalone HTML. */
            :root { --bg: #f7f4ee; --text: #1f1d1a; --muted: #6a6258; }
            @media (prefers-color-scheme: dark) {
              :root { --bg: #1e1b18; --text: #ece7df; --muted: #a59b8d; }
            }
            body {
              font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif;
              margin: 0; background: var(--bg); color: var(--text);
            }
            main { max-width: 34rem; margin: 0 auto; padding: 2rem 1.25rem; }
            h1 { font-size: 1.1rem; margin: 0 0 0.75rem; }
            p { line-height: 1.45; color: var(--muted); margin: 0.5rem 0; }
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
        (function() {
            var nativeToken = '\(tokenLiteral)';
            var nativeTokenSentinel = '__fichero_native_token__';
            window.ficheroToken = nativeTokenSentinel;
            window.ficheroLibrary = '\(libraryLiteral)';
            if (window.ficheroNativeFetchInstalled) { return; }
            window.ficheroNativeFetchInstalled = true;
            var nativeFetch = window.fetch.bind(window);
            window.fetch = function(input, init) {
                var requestURL = typeof input === 'string' ? input : input?.url;
                var url = new URL(requestURL || '', window.location.href);
                var nextInit = init ? Object.assign({}, init) : {};
                var headers = new Headers(nextInit.headers || (input && input.headers) || {});
                if (url.origin === window.location.origin
                    && headers.get('Authorization') === 'Bearer ' + nativeTokenSentinel) {
                    headers.set('Authorization', 'Bearer ' + nativeToken);
                    nextInit.headers = headers;
                }
                return nativeFetch(input, nextInit);
            };
            // Seal the override so a later page script (or an XSS via document
            // names / OCR / entity names in the templates) can't re-wrap
            // window.fetch to capture the real token swapped into proxied
            // requests (#3223). window.ficheroToken already exposes only a
            // non-functional sentinel; this closes the remaining exfil path.
            // (Complete defense-in-depth — preventing an XSS from *using* the
            // API — needs a read-only library-scoped view token from the engine.)
            try {
                Object.defineProperty(window, 'fetch', {
                    value: window.fetch,
                    writable: false,
                    configurable: false
                });
            } catch (sealError) {
                // Older WebKit that rejects redefining fetch: the override still
                // applies, it just stays re-wrappable. Non-fatal.
            }
        })();
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

    // MARK: - System theme injection (#1481 / #3683)

    /// The resolved reader palette + base text size for the current appearance,
    /// bridged from the platform's SEMANTIC colors/fonts so the WebKit reader
    /// matches the native app in light AND dark. Colors, fonts, AND base size are
    /// all injected, on macOS AND iOS — closing the previously-unthemed-reader-
    /// on-iOS gap (#3683).
    private struct ReaderTheme {
        let background, panel, text, muted, line, accent, accentSoft: String
        let selectionBg, selectionText: String
        /// Semantic body point size (Dynamic Type on iOS). The Reader font-scale
        /// override (#3681) multiplies this before injection.
        let baseSizePx: Int
    }

    /// A platform SEMANTIC color as an sRGB `rgba(...)` CSS string.
    #if canImport(AppKit)
    private static func cssColor(_ color: NSColor) -> String {
        let resolved = color.usingColorSpace(.sRGB) ?? NSColor.black
        let red = Int((resolved.redComponent * 255).rounded())
        let green = Int((resolved.greenComponent * 255).rounded())
        let blue = Int((resolved.blueComponent * 255).rounded())
        return String(format: "rgba(%d, %d, %d, %.3f)", red, green, blue, resolved.alphaComponent)
    }
    #elseif canImport(UIKit)
    private static func cssColor(_ color: UIColor) -> String {
        let resolved = color.resolvedColor(with: UITraitCollection.current)
        var red: CGFloat = 0, green: CGFloat = 0, blue: CGFloat = 0, alpha: CGFloat = 0
        guard resolved.getRed(&red, green: &green, blue: &blue, alpha: &alpha) else {
            return "rgba(0, 0, 0, 1.000)"
        }
        return String(
            format: "rgba(%d, %d, %d, %.3f)",
            Int((red * 255).rounded()), Int((green * 255).rounded()),
            Int((blue * 255).rounded()), alpha
        )
    }
    #endif

    /// The reader typography font stacks — the single Swift-side source that
    /// keeps the WebKit reader's fonts identical to the app (matches the template
    /// defaults, and now overrides them so both stay in lockstep).
    private static let readerFontSystem =
        "-apple-system, BlinkMacSystemFont, \"SF Pro Text\", system-ui, sans-serif"
    private static let readerFontMono =
        "ui-monospace, \"SF Mono\", SFMono-Regular, Menlo, monospace"

    /// Neutral fallback matching the template's light default, used when no
    /// platform appearance is resolvable.
    private static let fallbackReaderTheme = ReaderTheme(
        background: "rgba(247, 244, 238, 1.000)", panel: "rgba(255, 255, 255, 0.850)",
        text: "rgba(31, 29, 26, 1.000)", muted: "rgba(106, 98, 88, 1.000)",
        line: "rgba(64, 53, 39, 0.140)", accent: "rgba(13, 107, 111, 1.000)",
        accentSoft: "rgba(13, 107, 111, 0.140)",
        selectionBg: "rgba(13, 107, 111, 0.300)", selectionText: "rgba(31, 29, 26, 1.000)",
        baseSizePx: 14
    )

    /// Semantic `.body` point size (Dynamic Type on iOS) the reader body text
    /// derives from — so Dynamic Type is folded into the base before the #3681
    /// user scale multiplies it.
    @MainActor
    static func readerBaseSize() -> Int {
        #if canImport(AppKit)
        return Int(NSFont.preferredFont(forTextStyle: .body).pointSize.rounded())
        #elseif canImport(UIKit)
        return Int(UIFont.preferredFont(forTextStyle: .body).pointSize.rounded())
        #else
        return 14
        #endif
    }

    /// Resolve the semantic palette for the current appearance, per platform.
    @MainActor
    private static func resolveReaderTheme() -> ReaderTheme {
        #if canImport(AppKit)
        var theme: ReaderTheme?
        NSApp.effectiveAppearance.performAsCurrentDrawingAppearance {
            theme = ReaderTheme(
                background: cssColor(.textBackgroundColor),
                panel: cssColor(.controlBackgroundColor),
                text: cssColor(.textColor),
                muted: cssColor(.secondaryLabelColor),
                line: cssColor(.separatorColor),
                accent: cssColor(.controlAccentColor),
                accentSoft: cssColor(.controlAccentColor.withAlphaComponent(0.14)),
                // Bridge the macOS system selection color so ::selection matches
                // the user's accent / appearance, not the browser default (#1481).
                selectionBg: cssColor(.selectedTextBackgroundColor),
                selectionText: cssColor(.selectedTextColor),
                baseSizePx: readerBaseSize()
            )
        }
        return theme ?? fallbackReaderTheme
        #elseif canImport(UIKit)
        // iOS has no `selectedTextBackgroundColor`; approximate with the app tint.
        let accent = UIColor.tintColor
        return ReaderTheme(
            background: cssColor(.systemBackground),
            panel: cssColor(.secondarySystemBackground),
            text: cssColor(.label),
            muted: cssColor(.secondaryLabel),
            line: cssColor(.separator),
            accent: cssColor(accent),
            accentSoft: cssColor(accent.withAlphaComponent(0.14)),
            selectionBg: cssColor(accent.withAlphaComponent(0.30)),
            selectionText: cssColor(.label),
            baseSizePx: readerBaseSize()
        )
        #else
        return fallbackReaderTheme
        #endif
    }

    /// CSS that overrides the template's `:root` palette + typography with the
    /// live SEMANTIC system colors/fonts for the current appearance, so the
    /// WebKit reader matches the native app exactly — colors, accent, dark mode,
    /// font stack, and base text size. Theming lives here (Swift) by design: the
    /// backend never sniffs the OS. Cross-platform (macOS + iOS) — #3683.
    @MainActor
    static func systemThemeCSS() -> String {
        let theme = resolveReaderTheme()
        // The reader body size = semantic base × the user's Reader font scale
        // (#3681). Dynamic Type is already in `baseSizePx`; the scale composes.
        let scaledSize = Int((Double(theme.baseSizePx) * ViewSettings.FontScale.readerScale()).rounded())
        return """
        :root{\
        --bg: \(theme.background);--panel: \(theme.panel);--text: \(theme.text);\
        --muted: \(theme.muted);--line: \(theme.line);--accent: \(theme.accent);\
        --accent-soft: \(theme.accentSoft);\
        --font-system: \(readerFontSystem);--font-mono: \(readerFontMono);\
        --reader-base-size: \(scaledSize)px;--reader-text-wrap: \(ReaderTextWrap.currentCSS());\
        }html,body{background:transparent!important;}
        ::selection{background-color:\(theme.selectionBg);color:\(theme.selectionText);}
        """
    }

    /// JS that injects (or refreshes) the system-theme `<style>` element so it
    /// overrides the template defaults regardless of load timing. Cross-platform.
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
        \(paragraphWidontFallbackScript)
        """
    }

    /// Widont fallback for paragraph wrapping (#3684): only runs on WebKit WITHOUT
    /// `text-wrap: pretty` (older than the Golden Gate target — a no-op there), and
    /// only when the Reader wrap mode is "tidy" (`--reader-text-wrap: pretty`). It
    /// joins each paragraph's last two words with a non-breaking space so a single
    /// word can't strand on the last line. Idempotent (dataset flag), fail-safe.
    private static let paragraphWidontFallbackScript = """
    (function() {
        try {
            if (window.CSS && CSS.supports && CSS.supports('text-wrap', 'pretty')) { return; }
            var mode = getComputedStyle(document.documentElement)
                .getPropertyValue('--reader-text-wrap').trim();
            if (mode !== 'pretty') { return; }
            var ps = document.querySelectorAll('p');
            for (var i = 0; i < ps.length; i++) {
                var p = ps[i];
                if (p.dataset.ficheroWidont) { continue; }
                p.innerHTML = p.innerHTML.replace(/\\s+(\\S+)\\s*$/, '\\u00A0$1');
                p.dataset.ficheroWidont = '1';
            }
        } catch (widontError) { /* wrapping is cosmetic; never break the reader */ }
    })();
    """

    // swiftlint:disable:next function_body_length
    static func scrollSyncScript(pageCount: Int?) -> String {
        let count = max(pageCount ?? 0, 0)
        return """
        (function() {
            window.ficheroPageCount = \(count);
            window.ficheroScrollSyncSequence = window.ficheroScrollSyncSequence || 0;
            function scroller() {
                return document.querySelector('.content') || document.scrollingElement;
            }
            function pageAnchors() {
                return Array.from(document.querySelectorAll('.transcript [data-page]'));
            }
            function installPageAnchors() {
                if (pageAnchors().length > 0) { return pageAnchors(); }
                var transcript = document.querySelector('.transcript');
                if (!transcript) { return []; }
                var walker = document.createTreeWalker(transcript, NodeFilter.SHOW_TEXT);
                var nodes = [];
                var node;
                while ((node = walker.nextNode())) {
                    nodes.push(node);
                }
                nodes.forEach(function(textNode) {
                    var text = textNode.nodeValue;
                    var regex = /(^|\\n)(Page\\s+(\\d+)\\b)/g;
                    var match;
                    var lastIndex = 0;
                    var fragment = document.createDocumentFragment();
                    while ((match = regex.exec(text)) !== null) {
                        var prefix = match[1] || "";
                        var headingStart = match.index + prefix.length;
                        fragment.appendChild(document.createTextNode(text.slice(lastIndex, headingStart)));
                        var anchor = document.createElement('span');
                        anchor.dataset.page = match[3];
                        anchor.style.position = 'relative';
                        anchor.style.top = '-8px';
                        anchor.setAttribute('aria-hidden', 'true');
                        fragment.appendChild(anchor);
                        fragment.appendChild(document.createTextNode(text.slice(headingStart, regex.lastIndex)));
                        lastIndex = regex.lastIndex;
                    }
                    if (lastIndex === 0) { return; }
                    fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
                    textNode.parentNode.replaceChild(fragment, textNode);
                });
                return pageAnchors();
            }
            // Measured per-page offset table: each anchor marks a page's real
            // start, so its measured scroll offset is that page's top and the
            // next anchor's offset is its bottom. Real DOM measurement (never a
            // proportional scrollTop/maxScroll estimate) is what makes the map
            // exact when pages have unequal transcript heights (#3226).
            function pageOffsets() {
                var root = scroller();
                var anchors = installPageAnchors();
                if (!root || anchors.length === 0) { return []; }
                var rootTop = (root === document.scrollingElement)
                    ? 0
                    : root.getBoundingClientRect().top;
                var offsets = anchors.map(function(anchor) {
                    var rect = anchor.getBoundingClientRect();
                    return { page: Number(anchor.dataset.page), top: rect.top - rootTop + root.scrollTop };
                }).filter(function(entry) { return Number.isFinite(entry.page); });
                offsets.sort(function(a, b) { return a.top - b.top; });
                return offsets;
            }
            // The page whose measured [top, nextTop) offset range contains the
            // current reading line — a line a little below the viewport top, so a
            // page's body wins over the trailing sliver of the previous page.
            function pageForScroll() {
                var root = scroller();
                var offsets = pageOffsets();
                if (!root || offsets.length === 0) { return null; }
                var readingLine = root.scrollTop + Math.min(root.clientHeight * 0.25, 80);
                var current = offsets[0].page;
                for (var i = 0; i < offsets.length; i++) {
                    if (offsets[i].top <= readingLine) { current = offsets[i].page; } else { break; }
                }
                return current;
            }
            window.ficheroScrollToPage = function(pageNumber, pageCount) {
                var count = pageCount || window.ficheroPageCount || 0;
                var page = Number(pageNumber);
                var anchor = document.querySelector('.transcript [data-page="' + page + '"]');
                var root = scroller();
                if (!anchor) {
                    installPageAnchors();
                    anchor = document.querySelector('.transcript [data-page="' + page + '"]');
                }
                if (!anchor || !root || count <= 1 || !Number.isFinite(page)) { return; }
                // Bump the sequence + arm the echo guard so the programmatic
                // scroll this triggers doesn't post the same page straight back
                // (the feedback loop the Swift time-windows used to mask). The
                // guard clears once the scroll has settled (two frames).
                window.ficheroScrollSyncSequence += 1;
                window.ficheroSuppressScrollPost = true;
                window.ficheroScrollSyncLastPage = page;
                anchor.scrollIntoView({ block: 'start', inline: 'nearest' });
                window.requestAnimationFrame(function() {
                    window.requestAnimationFrame(function() {
                        window.ficheroSuppressScrollPost = false;
                    });
                });
            };
            function postPage(page) {
                var count = window.ficheroPageCount || 0;
                var handler = window.webkit?.messageHandlers?.ficheroBridge;
                if (!handler || count <= 1 || page === null || page === window.ficheroScrollSyncLastPage) { return; }
                window.ficheroScrollSyncLastPage = page;
                handler.postMessage({ kind: 'pageSelected', pageNumber: page });
            }
            function onScroll() {
                if (window.ficheroSuppressScrollPost || window.ficheroScrollRAF) { return; }
                window.ficheroScrollRAF = window.requestAnimationFrame(function() {
                    window.ficheroScrollRAF = null;
                    var page = pageForScroll();
                    if (page !== null) { postPage(page); }
                });
            }
            function installScrollSync() {
                var root = scroller();
                var count = window.ficheroPageCount || 0;
                installPageAnchors();
                if (!root || count <= 1) { return; }
                var target = (root === document.scrollingElement) ? document : root;
                if (window.ficheroScrollTarget && window.ficheroScrollHandler) {
                    window.ficheroScrollTarget.removeEventListener('scroll', window.ficheroScrollHandler);
                }
                window.ficheroScrollTarget = target;
                window.ficheroScrollHandler = onScroll;
                target.addEventListener('scroll', onScroll, { passive: true });
            }
            installScrollSync();
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
    /// Reader text font scale (#3681). Bound to the shared key so a change
    /// re-invokes `updateNSView`, which re-injects the scaled `--reader-base-size`
    /// live — no reload (systemThemeCSS reads the current scale).
    @AppStorage(ViewSettings.FontScale.readerKey)
    private var readerFontScale = ViewSettings.FontScale.defaultValue
    /// Reader paragraph wrapping (#3684). Also re-injected on change.
    @AppStorage(ReaderTextWrap.storageKey)
    private var readerTextWrap = ReaderTextWrap.tidy
    @Environment(KGFocusState.self) private var kgFocusState
    /// Per-window source-navigation bus (#3437). Captured into the coordinator
    /// in `updateNSView` — a WKScriptMessageHandler callback fires async, outside
    /// view evaluation, where reading `@Environment` directly is unsafe.
    @Environment(ClaimSourceNavigationState.self) private var claimSourceNavigationState: ClaimSourceNavigationState?

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

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        var parent: DocumentKGWebPane
        /// Last Reader font scale re-injected (#3681); NaN so the first compare fires.
        var lastReaderFontScale: Double = .nan
        /// Last Reader wrap mode re-injected (#3684); "" so the first compare fires.
        var lastReaderTextWrap: String = ""
        /// Per-window source-navigation bus, captured from the environment each
        /// `updateNSView` so async bridge callbacks route to THIS window (#3437).
        var claimSourceNavigationState: ClaimSourceNavigationState?
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
    /// Reader text font scale (#3681) — see the macOS pane. Re-injects the scaled
    /// `--reader-base-size` live on change.
    @AppStorage(ViewSettings.FontScale.readerKey)
    private var readerFontScale = ViewSettings.FontScale.defaultValue
    /// Reader paragraph wrapping (#3684). Also re-injected on change.
    @AppStorage(ReaderTextWrap.storageKey)
    private var readerTextWrap = ReaderTextWrap.tidy
    @Environment(KGFocusState.self) private var kgFocusState
    /// Per-window source-navigation bus (#3437); captured into the coordinator
    /// in `updateUIView` for the async bridge callback.
    @Environment(ClaimSourceNavigationState.self) private var claimSourceNavigationState: ClaimSourceNavigationState?

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

    final class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        var parent: DocumentKGWebPane
        /// Last Reader font scale re-injected (#3681); NaN so the first compare fires.
        var lastReaderFontScale: Double = .nan
        /// Last Reader wrap mode re-injected (#3684); "" so the first compare fires.
        var lastReaderTextWrap: String = ""
        /// Per-window source-navigation bus, captured each `updateUIView` (#3437).
        var claimSourceNavigationState: ClaimSourceNavigationState?
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
