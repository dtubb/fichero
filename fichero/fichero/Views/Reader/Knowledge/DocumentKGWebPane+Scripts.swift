import Foundation

extension DocumentKGPaneRoute {
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

    /// Generates the JavaScript for scroll synchronization between the native
    /// page picker and the web view transcript.
    static func scrollSyncScript(pageCount: Int?) -> String {
        let count = max(pageCount ?? 0, 0)
        return scrollSyncCore(count: count)
    }

    private static func scrollSyncCore(count: Int) -> String {
        let helperFunctions = scrollSyncHelperFunctions()
        let eventHandlers = scrollSyncEventHandlers()
        return """
        (function() {
            window.ficheroPageCount = \(count);
            window.ficheroScrollSyncSequence = window.ficheroScrollSyncSequence || 0;
            \(helperFunctions)
            \(eventHandlers)
            installScrollSync();
        })();
        """
    }

    private static func scrollSyncHelperFunctions() -> String {
        let scrollerAndAnchors = scrollerAndAnchorHelpers()
        let offsetCalculation = pageOffsetCalculationHelpers()
        return "\(scrollerAndAnchors)\n\(offsetCalculation)"
    }

    private static func scrollerAndAnchorHelpers() -> String {
        """
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
        """
    }

    private static func pageOffsetCalculationHelpers() -> String {
        """
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
        // #4373: which page a CLICKED node belongs to — the nearest page anchor
        // at or above it. An empty, untranscribed page is resolved exactly like
        // any other: the anchors come from the page structure, not from whether
        // a page has text, so an empty page is clickable rather than inert.
        function pageForNode(node) {
            var element = (node && node.nodeType === 1) ? node : (node ? node.parentElement : null);
            var root = scroller();
            var offsets = pageOffsets();
            if (!element || !root || offsets.length === 0) { return null; }
            var rootTop = (root === document.scrollingElement)
                ? 0
                : root.getBoundingClientRect().top;
            var top = element.getBoundingClientRect().top - rootTop + root.scrollTop;
            var current = offsets[0].page;
            for (var i = 0; i < offsets.length; i++) {
                // +1px of slack: a click lands ON the heading whose anchor sits
                // a hair above it, and strict `<=` would attribute it upward.
                if (offsets[i].top <= top + 1) { current = offsets[i].page; } else { break; }
            }
            return current;
        }
        """
    }

    private static func scrollSyncEventHandlers() -> String {
        """
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
        // #4373: a click on a page is an instruction to select it; a scroll past
        // it is not. Separate message kind, because the app is allowed to move
        // the library selection and the preview for one and not the other
        // (#1463).
        function onTranscriptClick(event) {
            // A drag that selected text is reading, not navigating. Selecting a
            // quote must never yank the library out from under the user.
            var selection = window.getSelection();
            if (selection && !selection.isCollapsed) { return; }
            var page = pageForNode(event.target);
            var handler = window.webkit?.messageHandlers?.ficheroBridge;
            if (!handler || page === null || !Number.isFinite(page)) { return; }
            // Deliberately NOT gated on ficheroScrollSyncLastPage: clicking the
            // page you are already reading is still a request to select it.
            handler.postMessage({ kind: 'pageActivated', pageNumber: page });
        }
        function installPageClicks() {
            var transcript = document.querySelector('.transcript');
            if (!transcript) { return; }
            if (window.ficheroPageClickTarget && window.ficheroPageClickHandler) {
                window.ficheroPageClickTarget.removeEventListener(
                    'click', window.ficheroPageClickHandler
                );
            }
            window.ficheroPageClickTarget = transcript;
            window.ficheroPageClickHandler = onTranscriptClick;
            transcript.addEventListener('click', onTranscriptClick);
        }
        function installScrollSync() {
            var root = scroller();
            var count = window.ficheroPageCount || 0;
            installPageAnchors();
            // Installed BEFORE the single-page bail-out below: scroll sync is
            // pointless in a one-page document, but a click still has to select
            // that page.
            installPageClicks();
            if (!root || count <= 1) { return; }
            var target = (root === document.scrollingElement) ? document : root;
            if (window.ficheroScrollTarget && window.ficheroScrollHandler) {
                window.ficheroScrollTarget.removeEventListener('scroll', window.ficheroScrollHandler);
            }
            window.ficheroScrollTarget = target;
            window.ficheroScrollHandler = onScroll;
            target.addEventListener('scroll', onScroll, { passive: true });
        }
        """
    }

    /// Escapes a string for safe injection into JavaScript string literals.
    static func jsStringLiteral(_ raw: String) -> String {
        raw
            .replacingOccurrences(of: "\\", with: "\\\\")
            .replacingOccurrences(of: "'", with: "\\'")
            .replacingOccurrences(of: "\r", with: "")
            .replacingOccurrences(of: "\n", with: "\\n")
    }
}
