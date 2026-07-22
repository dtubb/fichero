import SwiftUI
import WebKit

/// Renders a workflow's LangGraph diagram from **mermaid source** in a
/// `WKWebView`.
///
/// The engine's `…/workflows/{id}/visualization` endpoint returns
/// `WorkflowVisualizationResponse` JSON whose `mermaid_code` field is mermaid
/// diagram source — NOT image bytes. We render it live by loading a
/// self-contained HTML page that inlines a **bundled** `mermaid.min.js`
/// (a static app resource; never fetched from the engine, honouring the
/// offline/loopback posture) plus a `<pre class="mermaid">` holding the source.
///
/// The page is theme-aware via `prefers-color-scheme` (CSS palette + mermaid's
/// own `dark`/`default` theme) and degrades gracefully: empty source shows a
/// SwiftUI placeholder, and mermaid parse failures show an in-page message
/// instead of crashing or blanking.
struct WorkflowMermaidView: View {
    let mermaidCode: String

    private var trimmedCode: String {
        mermaidCode.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var body: some View {
        if trimmedCode.isEmpty {
            VStack(spacing: 8) {
                Image(systemName: "flowchart")
                    .font(.largeTitle)
                    .foregroundStyle(.secondary)
                Text("No diagram")
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            MermaidWebView(html: MermaidHTML.page(mermaidCode: trimmedCode))
        }
    }
}

/// Builds the self-contained mermaid HTML page.
enum MermaidHTML {
    /// Bundled `mermaid.min.js`, read once and cached. Missing resource yields
    /// an empty string, and `page(mermaidCode:)` renders a "diagram engine
    /// unavailable" message rather than a blank page.
    private static let mermaidJS: String = {
        guard let url = Bundle.main.url(forResource: "mermaid.min", withExtension: "js"),
              let source = try? String(contentsOf: url, encoding: .utf8) else {
            return ""
        }
        return source
    }()

    /// Escape text for safe insertion into HTML element content. The browser
    /// un-escapes back to the original characters, so mermaid sees the raw
    /// source via `textContent`.
    private static func escape(_ text: String) -> String {
        text.replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
    }

    static func page(mermaidCode: String) -> String {
        let js = mermaidJS
        guard !js.isEmpty else {
            return unavailablePage()
        }
        return """
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <style>
            :root { --bg: #f7f4ee; --text: #1f1d1a; --muted: #6a6258; }
            @media (prefers-color-scheme: dark) {
              :root { --bg: #1e1b18; --text: #ece7df; --muted: #a59b8d; }
            }
            html, body { margin: 0; height: 100%; }
            body {
              font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", system-ui, sans-serif;
              background: var(--bg); color: var(--text);
              display: flex; align-items: center; justify-content: center;
            }
            #diagram { padding: 1rem; }
            #diagram svg { max-width: 100%; height: auto; }
            #message { color: var(--muted); padding: 1.25rem; text-align: center; line-height: 1.45; }
          </style>
        </head>
        <body>
          <div id="diagram"><pre class="mermaid">\(escape(mermaidCode))</pre></div>
          <div id="message" hidden></div>
          <script>\(js)</script>
          <script>
            (function () {
              var dark = window.matchMedia &&
                window.matchMedia('(prefers-color-scheme: dark)').matches;
              try {
                mermaid.initialize({
                  startOnLoad: false,
                  securityLevel: 'strict',
                  theme: dark ? 'dark' : 'default'
                });
                mermaid.run({ querySelector: '.mermaid' }).catch(showError);
              } catch (err) {
                showError(err);
              }
              function showError(err) {
                var diagram = document.getElementById('diagram');
                var message = document.getElementById('message');
                if (diagram) { diagram.hidden = true; }
                if (message) {
                  message.hidden = false;
                  message.textContent = 'Could not render this diagram.';
                }
              }
            })();
          </script>
        </body>
        </html>
        """
    }

    private static func unavailablePage() -> String {
        """
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <style>
            :root { --bg: #f7f4ee; --muted: #6a6258; }
            @media (prefers-color-scheme: dark) {
              :root { --bg: #1e1b18; --muted: #a59b8d; }
            }
            body {
              font-family: -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
              margin: 0; background: var(--bg); color: var(--muted);
              display: flex; align-items: center; justify-content: center;
              height: 100vh; text-align: center; padding: 1.25rem; line-height: 1.45;
            }
          </style>
        </head>
        <body>Diagram renderer is unavailable.</body>
        </html>
        """
    }
}

/// Minimal `WKWebView` wrapper that renders a static HTML string (no navigation,
/// no auth, no network — the page is fully self-contained). Distinct from
/// `FicheroWebView`, which loads remote URLs.
#if os(macOS)
struct MermaidWebView: NSViewRepresentable {
    let html: String

    func makeNSView(context: Context) -> WKWebView {
        let webView = WKWebView(frame: .zero)
        webView.setValue(false, forKey: "drawsBackground")
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        guard context.coordinator.loadedHTML != html else { return }
        context.coordinator.loadedHTML = html
        webView.loadHTMLString(html, baseURL: nil)
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator {
        var loadedHTML: String?
    }
}
#elseif os(iOS) || os(visionOS)
struct MermaidWebView: UIViewRepresentable {
    let html: String

    func makeUIView(context: Context) -> WKWebView {
        let webView = WKWebView(frame: .zero)
        webView.isOpaque = false
        webView.backgroundColor = .clear
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        guard context.coordinator.loadedHTML != html else { return }
        context.coordinator.loadedHTML = html
        webView.loadHTMLString(html, baseURL: nil)
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator {
        var loadedHTML: String?
    }
}
#endif
