#if canImport(AppKit)
import AppKit
import Foundation
import WebKit

/// #6111: the WebKit-backed unit tests need WebKit's web-content process. Under a sandboxed shell (an agent's
/// `xcodebuild test`) it cannot start ("Connection init failed ... error 159 - Sandbox restriction"), and the tests
/// then fail for a reason that has nothing to do with the code. This loads a blank page ONCE and, if that does not
/// finish, throws the cause in words. It is a failure, never a skip: a real red must not hide behind the environment.
@MainActor
enum WebKitProbe {
    struct CouldNotStart: Error, CustomStringConvertible {
        let webKitSaid: String
        var description: String {
            "WebKit could not start: the shell running xcodebuild is sandboxed; run the Mac unit step from a "
                + "GUI-session shell (#6111). WebKit said: \(webKitSaid)"
        }
    }

    private final class Loaded: NSObject, WKNavigationDelegate {
        private var resume: ((Result<Void, any Error>) -> Void)?

        func load(into webView: WKWebView, seconds: TimeInterval) async throws {
            try await withCheckedThrowingContinuation { continuation in
                resume = { continuation.resume(with: $0) }
                webView.navigationDelegate = self
                webView.loadHTMLString("<html><body></body></html>", baseURL: nil)
                DispatchQueue.main.asyncAfter(deadline: .now() + seconds) { [weak self] in
                    self?.finish(.failure(NSError(
                        domain: "WebKitProbe", code: 1,
                        userInfo: [NSLocalizedDescriptionKey: "a blank page did not load in \(Int(seconds)) seconds"])))
                }
            }
        }

        private func finish(_ result: Result<Void, any Error>) {
            guard let resume else { return }
            self.resume = nil
            resume(result)
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { finish(.success(())) }
        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: any Error) {
            finish(.failure(error))
        }
        func webView(
            _ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: any Error
        ) { finish(.failure(error)) }
    }

    private static var outcome: Result<Void, CouldNotStart>?

    /// Returns when WebKit has loaded a blank page; throws `CouldNotStart` (the same answer every time) when it did not.
    static func requireStarted() async throws {
        if outcome == nil {
            let webView = WKWebView(frame: NSRect(x: 0, y: 0, width: 100, height: 100))
            let watcher = Loaded()  // the web view holds its delegate weakly
            do {
                try await watcher.load(into: webView, seconds: 10)
                outcome = .success(())
            } catch {
                outcome = .failure(CouldNotStart(webKitSaid: String(describing: error)))
            }
        }
        try outcome?.get()
    }
}
#endif
