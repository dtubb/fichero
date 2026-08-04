import Foundation

/// Is THIS PROCESS running under the App Sandbox?
///
/// Its own file because it is not one subsystem's business: whether the app is
/// sandboxed decides what `Path.home()` means to a child engine, whether
/// security-scoped bookmarks are needed, and where `.libraryDirectory` resolves.
/// Three separate call sites had been answering it by proxy.
///
/// The proxy was `#if FICHERO_APP_STORE`, on the premise that App Store was the
/// only sandboxed channel. That premise died when Dev builds became sandboxed
/// (2026-07-29) and nothing re-checked the places that depended on it — which is
/// how a sandboxed Dev engine came to be told it was not sandboxed, received no
/// bookmarks, and refused every library the user created (2026-08-04).
///
/// A build flag cannot answer a runtime question. This asks the process.
enum SandboxEnvironment {
    /// `APP_SANDBOX_CONTAINER_ID` is set by the system in every sandboxed
    /// process and by nothing else, so it answers directly rather than by proxy.
    static var isSandboxed: Bool {
        ProcessInfo.processInfo.environment["APP_SANDBOX_CONTAINER_ID"] != nil
    }
}
