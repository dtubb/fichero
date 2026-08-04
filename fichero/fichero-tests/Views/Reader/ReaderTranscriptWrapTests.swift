#if canImport(AppKit)
import AppKit
import Foundation
import Testing
import WebKit

/// The reader must wrap to the available width and never scroll horizontally
/// (#4385).
///
/// ## Which reader this is
///
/// The Reader's **Transcript** tab is WebKit, not SwiftUI: `DocumentKGSurface`
/// routes `.transcript` and `.digest` through `DocumentKGWebPane`, which loads
/// the engine's `document_view.html`. So the transcript's wrapping is CSS, and
/// the contract has to be measured in a real browser engine. (The Reader's
/// other text surface — the AppKit page-content pane — is a different surface
/// with its own contract; see `ReaderTextPaneWrapTests`.)
///
/// ## Why this test exists here and not in the backend suite
///
/// The CSS lives in the engine template, and the backend suite asserts the
/// declarations are present. That is what a text-matching suite can honestly
/// do, and its own comments say so: the true contract is
/// `scrollWidth <= clientWidth` at a narrow pane width with a long unbroken
/// token, and checking it needs a browser the backend suite does not have.
///
/// This target has one. A `WKWebView` is the same engine the reader ships,
/// so this measures the property the user actually experiences rather than
/// the spelling of the rules intended to produce it. A future edit that keeps
/// every asserted declaration but reintroduces the overflow some other way —
/// a new descendant with a min-width, a rule that re-enables `overflow-x` —
/// passes the backend suite and fails here, which is the whole point.
///
/// ## The input
///
/// A 4000-character unbroken token. `white-space: pre-wrap` wraps at existing
/// whitespace but cannot break a token that contains none, so one such run
/// sets a min-content width for the entire page and the pane scrolls sideways
/// to reveal it. On a handwriting-transcription corpus — a page returned as a
/// single line, a numeric sequence, a run where the model inferred no word
/// boundaries — that input is normal, not exotic.
@MainActor
struct ReaderTranscriptWrapTests {

    // MARK: - Measuring a real render

    /// What the browser reports about a rendered page. Every pair is
    /// "how wide the content is" against "how wide the box is": the defect is
    /// exactly the case where the first exceeds the second.
    private struct Overflow {
        let bodyScrollWidth: Int
        let bodyClientWidth: Int
        let containerScrollWidth: Int
        let containerClientWidth: Int
        let documentScrollWidth: Int
        let documentClientWidth: Int

        var transcriptOverflows: Bool { bodyScrollWidth > bodyClientWidth }
        var containerOverflows: Bool { containerScrollWidth > containerClientWidth }
        var documentOverflows: Bool { documentScrollWidth > documentClientWidth }

        var description: String {
            "body \(bodyScrollWidth)/\(bodyClientWidth), "
            + "container \(containerScrollWidth)/\(containerClientWidth), "
            + "document \(documentScrollWidth)/\(documentClientWidth)"
        }
    }

    /// Raised instead of hanging, so a WebKit that never starts fails as
    /// "the contract was not measured" rather than as a stalled suite.
    private struct LoadTimedOut: Error, CustomStringConvertible {
        var description: String {
            "the reader test page did not finish loading — WebKit could not "
            + "start in this test host, so the wrap contract was NOT measured"
        }
    }

    /// Awaits one load, and gives up rather than hanging.
    ///
    /// The watchdog is the point of the class. Without it, a WebContent process
    /// that never starts hangs the suite instead of failing it — and a hung
    /// suite reads as infrastructure trouble, not as "this contract went
    /// unchecked", which is the one conclusion that must never be silent.
    @MainActor
    private final class LoadWatcher: NSObject, WKNavigationDelegate {
        private var resume: ((Result<Void, any Error>) -> Void)?

        func load(_ html: String, into webView: WKWebView) async throws {
            try await withCheckedThrowingContinuation { continuation in
                resume = { continuation.resume(with: $0) }
                webView.navigationDelegate = self
                webView.loadHTMLString(html, baseURL: nil)
                DispatchQueue.main.asyncAfter(deadline: .now() + 30) { [weak self] in
                    self?.finish(.failure(LoadTimedOut()))
                }
            }
        }

        private func finish(_ result: Result<Void, any Error>) {
            guard let resume else { return }
            self.resume = nil
            resume(result)
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            finish(.success(()))
        }

        func webView(
            _ webView: WKWebView,
            didFail navigation: WKNavigation!,
            withError error: any Error
        ) {
            finish(.failure(error))
        }

        func webView(
            _ webView: WKWebView,
            didFailProvisionalNavigation navigation: WKNavigation!,
            withError error: any Error
        ) {
            finish(.failure(error))
        }
    }

    /// Render `html` at `width` points and report the widths.
    private static func measure(_ html: String, width: CGFloat) async throws -> Overflow {
        let webView = WKWebView(frame: NSRect(x: 0, y: 0, width: width, height: 480))
        // `WKWebView` holds its navigation delegate weakly, so the watcher has
        // to outlive the load explicitly.
        let watcher = LoadWatcher()
        try await watcher.load(html, into: webView)

        // `.content` is the pane's scroll container and `.transcript-page-body`
        // is the text itself; both are measured because a fix at one level can
        // leave the other overflowing.
        let probe = """
        (() => {
            const body = document.querySelector('.transcript-page-body');
            const container = document.querySelector('.content');
            const root = document.documentElement;
            return [
                body.scrollWidth, body.clientWidth,
                container.scrollWidth, container.clientWidth,
                document.body.scrollWidth, root.clientWidth
            ].join(',');
        })()
        """
        let raw = try await webView.evaluateJavaScript(probe)
        let numbers = ((raw as? String) ?? "").split(separator: ",").compactMap { Int($0) }
        try #require(numbers.count == 6, "the probe did not return six widths: \(String(describing: raw))")
        return Overflow(
            bodyScrollWidth: numbers[0], bodyClientWidth: numbers[1],
            containerScrollWidth: numbers[2], containerClientWidth: numbers[3],
            documentScrollWidth: numbers[4], documentClientWidth: numbers[5]
        )
    }

    // MARK: - The page under test

    /// The `<style>` block of the SHIPPED reader template.
    ///
    /// Read from disk rather than copied here on purpose: a copy would keep
    /// passing after someone changed the real template, which is the failure
    /// this test is supposed to catch.
    private static func shippedReaderCSS() throws -> String {
        let repositoryRoot = try AppSource.root()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let template = try String(
            contentsOf: repositoryRoot.appendingPathComponent(
                "fichero-server/src/fichero_server/api/templates/document_view.html"),
            encoding: .utf8
        )
        guard let open = template.range(of: "<style>"),
              let close = template.range(of: "</style>") else {
            throw NoStyleBlock()
        }
        return String(template[open.upperBound..<close.lowerBound])
    }

    private struct NoStyleBlock: Error, CustomStringConvertible {
        var description: String {
            "document_view.html has no <style> block — the reader's wrapping "
            + "rules moved, and this test was measuring nothing"
        }
    }

    /// The transcript markup the template's own renderer emits, with `body`
    /// as the page text.
    private static func transcriptPage(css: String, body: String) -> String {
        """
        <!doctype html><html><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>\(css)</style></head>
        <body><div class="content"><section class="panel">
        <div class="transcript"><article class="transcript-page" data-page="1">
        <div class="page-marker">Page 1</div>
        <div class="transcript-page-body">\(body)</div>
        </article></div></section></div></body></html>
        """
    }

    /// One OCR line with no break opportunity anywhere in it.
    private static let unbreakableOCRLine = String(repeating: "8", count: 4000)

    // MARK: - The contract

    /// The reported defect, at the width where it hurts most.
    ///
    /// Narrow is the case the issue calls out: the reader is one of three
    /// panes, and someone who narrows it to make room for the library expects
    /// the transcription to reflow, not to become unreadable.
    @Test("a 4000-character unbroken OCR line does not widen the reader")
    func unbreakableLineDoesNotWidenTheReader() async throws {
        let html = Self.transcriptPage(css: try Self.shippedReaderCSS(), body: Self.unbreakableOCRLine)
        let measured = try await Self.measure(html, width: 200)

        #expect(!measured.transcriptOverflows, Comment(rawValue: measured.description))
        #expect(!measured.containerOverflows, Comment(rawValue: measured.description))
        #expect(!measured.documentOverflows, Comment(rawValue: measured.description))
    }

    /// "At every pane size, including very narrow." A rule that holds at one
    /// width and not another is a rule tuned to a screenshot.
    @Test("it holds at every pane width, not just the one that was checked")
    func itHoldsAtEveryPaneWidth() async throws {
        let css = try Self.shippedReaderCSS()
        for width in [120.0, 200.0, 400.0, 900.0] as [CGFloat] {
            let measured = try await Self.measure(
                Self.transcriptPage(css: css, body: Self.unbreakableOCRLine), width: width)
            let detail = "at \(Int(width))pt — \(measured.description)"
            #expect(!measured.transcriptOverflows, Comment(rawValue: detail))
            #expect(!measured.containerOverflows, Comment(rawValue: detail))
            #expect(!measured.documentOverflows, Comment(rawValue: detail))
        }
    }

    /// Ordinary prose must be unaffected — a wrap fix that also mangles normal
    /// text would be a worse reader, not a better one.
    @Test("ordinary prose still lays out inside the pane")
    func ordinaryProseIsUnaffected() async throws {
        let prose = String(repeating: "la palabra escrita en el archivo ", count: 200)
        let html = Self.transcriptPage(css: try Self.shippedReaderCSS(), body: prose)
        let measured = try await Self.measure(html, width: 300)

        #expect(!measured.transcriptOverflows, Comment(rawValue: measured.description))
        #expect(!measured.documentOverflows, Comment(rawValue: measured.description))
    }

    /// **The negative control.**
    ///
    /// Every assertion above is a "nothing overflows" check, and those pass
    /// trivially if the probe is broken, the markup does not match the real
    /// selectors, or WebKit silently rendered an empty page. So this feeds the
    /// probe the PRE-FIX styling and requires it to go red.
    ///
    /// A guardrail nobody has watched fire is a guardrail nobody knows works.
    ///
    /// #4533 — where the pre-fix overflow actually SHOWS, established with a
    /// standalone WKWebView probe over this exact reconstruction: the
    /// container overflows enormously (measured 35225 against a 200pt pane),
    /// but `.transcript-page-body` does NOT overflow ITSELF — `.transcript`
    /// is `display: grid`, so with `max-width` stripped the page track
    /// resolves to the item's min-content width and the body BOX balloons to
    /// content width (scrollWidth == clientWidth ≈ 35164). A box that grows
    /// does not overflow; its ancestors do. The old first assertion
    /// (`transcriptOverflows`) therefore reported honest blindness while the
    /// measurement was in fact seeing the bug one level up. The control now
    /// reads the two signals that genuinely fire pre-fix and are quiet on the
    /// shipped CSS: the container overflow, and the body box exceeding the
    /// pane width.
    @Test("the same measurement catches the pre-fix styling")
    func theMeasurementCatchesThePreFixStyling() async throws {
        // The three edits that, together, are what the reader used to do:
        // wrap only at whitespace, no bound on the page box, and a root
        // allowed to resolve wider than the pane.
        let preFixCSS = try Self.shippedReaderCSS()
            .replacingOccurrences(of: "overflow-wrap: anywhere;", with: "")
            .replacingOccurrences(of: "overflow-x: hidden;", with: "overflow-x: visible;")
            .replacingOccurrences(of: "max-width: 100%;", with: "")

        let measured = try await Self.measure(
            Self.transcriptPage(css: preFixCSS, body: Self.unbreakableOCRLine), width: 200)

        #expect(
            measured.containerOverflows,
            Comment(rawValue: """
            the pre-fix styling did NOT overflow the container \
            (\(measured.description)) — this measurement cannot detect the bug \
            it exists to detect, and the passing tests above prove nothing
            """)
        )
        #expect(
            measured.bodyClientWidth > 200,
            Comment(rawValue: """
            pre-fix, the grid track resolves the body BOX to its content width, \
            far past the 200pt pane — got \(measured.description); if this stays \
            pane-sized the reconstruction stopped reproducing the defect
            """)
        )
    }
}
#endif
