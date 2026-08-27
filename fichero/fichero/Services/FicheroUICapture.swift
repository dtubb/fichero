//
//  FicheroUICapture.swift
//  Fichero
//
//  In-process UI capture backing the AppleScript `screenshot` verb (#4535,
//  #4536). Lives apart from AppleScriptCommands.swift only for file length.
//

#if os(macOS)
import AppKit
import Foundation

/// Capture the app's own rendered UI to a PNG file (#4535, #4536).
///
/// One verb, one `view` parameter: omitted (or "window") captures the key
/// window's whole content; any other value names a view to capture by its
/// accessibility identifier. Rendering uses the DOCUMENTED offscreen pair
/// `bitmapImageRepForCachingDisplay(in:)` + `cacheDisplay(in:to:)` (renders
/// the view and its descendants; no screen-recording permission involved).
///
/// EMPIRICAL, not documented: SwiftUI's `.accessibilityIdentifier` reaches the
/// AX tree, but only some hosting-view descendants expose it via
/// `NSView.accessibilityIdentifier()` — which views are findable is a fact to
/// discover per build, so a miss FAILS with the identifiers that were actually
/// present rather than guessing (#4536 tracks first-class per-pane capture).
@objc(FicheroScreenshotCommand)
class FicheroScreenshotCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        guard let path = directParameter as? String, !path.isEmpty else {
            scriptErrorNumber = NSRequiredArgumentsMissingScriptError
            scriptErrorString = "Destination file path is required"
            return nil
        }
        let viewName = (evaluatedArguments?["view"] as? String) ?? "window"

        logger.info("AppleScript: screenshot view '\(viewName)' -> '\(path)'")
        do {
            return try MainActor.assumeIsolated {
                try FicheroUICapture.capture(viewNamed: viewName, to: path)
            }
        } catch {
            scriptErrorNumber = NSInternalScriptError
            scriptErrorString = String(describing: error)
            return nil
        }
    }
}

/// In-process UI capture shared by the screenshot verb.
@MainActor
enum FicheroUICapture {
    enum CaptureError: Error, CustomStringConvertible {
        case noWindow
        case viewNotFound(name: String, available: [String])
        case renderFailed(String)

        var description: String {
            switch self {
            case .noWindow:
                return "No visible window to capture — is a library window open?"
            case .viewNotFound(let name, let available):
                return "No view with accessibility identifier '\(name)'. "
                    + "Identifiers present: \(available.sorted().joined(separator: ", "))"
            case .renderFailed(let why):
                return "Could not render the capture: \(why)"
            }
        }
    }

    /// Render `viewName` ("window" = whole key-window content) into a PNG at
    /// `path`. Returns the absolute path written.
    static func capture(viewNamed viewName: String, to path: String) throws -> String {
        guard let window = NSApp.keyWindow ?? NSApp.orderedWindows.first(where: \.isVisible),
              let contentView = window.contentView
        else { throw CaptureError.noWindow }

        let target: NSView
        if viewName.isEmpty || viewName == "window" {
            target = contentView
        } else if let found = firstView(withIdentifier: viewName, under: contentView) {
            target = found
        } else {
            throw CaptureError.viewNotFound(
                name: viewName,
                available: allIdentifiers(under: contentView)
            )
        }

        guard let rep = target.bitmapImageRepForCachingDisplay(in: target.bounds) else {
            throw CaptureError.renderFailed("bitmapImageRepForCachingDisplay returned nil")
        }
        target.cacheDisplay(in: target.bounds, to: rep)
        guard let png = rep.representation(using: .png, properties: [:]) else {
            throw CaptureError.renderFailed("PNG encoding failed")
        }
        let url = URL(fileURLWithPath: (path as NSString).expandingTildeInPath)
        try FileManager.default.createDirectory(
            at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try png.write(to: url)
        return url.path
    }

    private static func firstView(withIdentifier name: String, under root: NSView) -> NSView? {
        var queue: [NSView] = [root]
        while !queue.isEmpty {
            let view = queue.removeFirst()
            if view.accessibilityIdentifier() == name { return view }
            queue.append(contentsOf: view.subviews)
        }
        return nil
    }

    private static func allIdentifiers(under root: NSView) -> [String] {
        var found = Set<String>()
        var queue: [NSView] = [root]
        while !queue.isEmpty {
            let view = queue.removeFirst()
            let identifier = view.accessibilityIdentifier()
            if !identifier.isEmpty { found.insert(identifier) }
            queue.append(contentsOf: view.subviews)
        }
        return Array(found)
    }
}
#endif
