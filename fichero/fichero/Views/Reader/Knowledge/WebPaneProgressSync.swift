import Foundation
import WebKit

/// Shared per-page progress sync used by BOTH platform coordinators (#4357).
///
/// Sends the run's busy pages only when the set changes, and sends a page's
/// text only when that page's content changes — so a live workflow updates the
/// reader by patching the affected page, never by reloading the WKWebView
/// (a reload loses scroll position and flashes: Every-Frame-Perfect).
///
/// Not actor-annotated, matching `WebPaneFindSync` and the coordinators that own
/// it — WebKit invokes everything here on the main thread.
final class WebPaneProgressSync {
    private var lastBusyPages: Set<Int>?
    private var lastSentContent: [Int: String] = [:]

    /// A fresh document (or a fresh DOM after `didFinish`) means nothing has
    /// been sent to this page yet.
    func reset() {
        lastBusyPages = nil
        lastSentContent = [:]
    }

    func sync(
        into webView: WKWebView,
        busyPages: Set<Int>,
        pageContent: [Int: String]
    ) {
        if lastBusyPages != busyPages {
            lastBusyPages = busyPages
            webView.evaluateJavaScript(DocumentKGPaneRoute.busyPagesScript(busyPages))
        }
        let changed = ReaderPageProgress.changedPatches(
            latest: pageContent,
            lastSent: lastSentContent
        )
        guard !changed.isEmpty else { return }
        for (number, text) in changed.sorted(by: { $0.key < $1.key }) {
            lastSentContent[number] = text
            webView.evaluateJavaScript(
                DocumentKGPaneRoute.pageContentScript(page: number, content: text)
            )
        }
    }
}

extension DocumentKGPaneRoute {
    /// Hand the in-page reader the run's target pages. An empty set clears every
    /// spinner, so a terminal state — or a dropped change stream (#4346/#4349) —
    /// can always stop them.
    static func busyPagesScript(_ pages: Set<Int>) -> String {
        let list = pages.sorted().map(String.init).joined(separator: ",")
        return "window.fichero?.setBusyPages([\(list)]);"
    }

    /// Patch ONE page's text in place as a run writes it.
    static func pageContentScript(page: Int, content: String) -> String {
        "window.fichero?.setPageContent(\(page), '\(jsStringLiteral(content))');"
    }
}
