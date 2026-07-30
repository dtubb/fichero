import SwiftUI
import WebKit

/// Renders a self-contained HTML or SVG rendition string in WebKit (#4329).
///
/// Used by `DocumentCanvas` for `conversion` artifacts: the model-generated
/// markup (already sanitized server-side) is loaded as a local string with
/// JavaScript disabled — a rendition is a document, never active content.
/// No network navigation: the content is inline and links are inert.
struct WebContentCanvas {
    enum Kind {
        case html
        case svg
    }

    let content: String
    let kind: Kind

    /// The document string WebKit loads. SVG gets a minimal centering shell so
    /// a bare `<svg>` renders scaled-to-fit rather than clipped at the origin.
    var htmlDocument: String {
        switch kind {
        case .html:
            return content
        case .svg:
            return """
            <!doctype html>
            <meta charset="utf-8">
            <style>
              html, body { margin: 0; height: 100%; background: transparent; }
              body { display: grid; place-items: center; }
              svg { max-width: 100%; max-height: 100vh; height: auto; }
            </style>
            \(content)
            """
        }
    }

    static func makeWebView() -> WKWebView {
        let configuration = WKWebViewConfiguration()
        // Renditions are static documents — never execute scripts, even if
        // something slipped past server-side sanitization.
        configuration.defaultWebpagePreferences.allowsContentJavaScript = false
        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.underPageBackgroundColor = .clear
        #if !os(macOS)
        webView.isOpaque = false
        webView.backgroundColor = .clear
        #endif
        return webView
    }
}

#if os(macOS)
extension WebContentCanvas: NSViewRepresentable {
    func makeNSView(context: Context) -> WKWebView {
        let webView = Self.makeWebView()
        webView.loadHTMLString(htmlDocument, baseURL: nil)
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        // Reload only when the content actually changed — comparing against the
        // last-loaded string avoids a visible flash on unrelated state updates.
        if context.coordinator.loadedContent != htmlDocument {
            context.coordinator.loadedContent = htmlDocument
            webView.loadHTMLString(htmlDocument, baseURL: nil)
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(loadedContent: htmlDocument)
    }
}
#else
extension WebContentCanvas: UIViewRepresentable {
    func makeUIView(context: Context) -> WKWebView {
        let webView = Self.makeWebView()
        webView.loadHTMLString(htmlDocument, baseURL: nil)
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        if context.coordinator.loadedContent != htmlDocument {
            context.coordinator.loadedContent = htmlDocument
            webView.loadHTMLString(htmlDocument, baseURL: nil)
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(loadedContent: htmlDocument)
    }
}
#endif

extension WebContentCanvas {
    final class Coordinator {
        var loadedContent: String

        init(loadedContent: String) {
            self.loadedContent = loadedContent
        }
    }
}
