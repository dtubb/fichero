//
//  FicheroUICapture.swift
//  Fichero
//
//  The screenshot UI verb (#5453, `openapi.ui.screenshot`; first #4535, #4536): the app draws its own
//  window, or one pane of it, into a PNG. No screen recording, so no permission prompt.
//

#if os(macOS)
import AppKit
#else
import UIKit
#endif
import Foundation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "AppleScript")

#if os(macOS)
/// `screenshot "<path>" [of pane "<name>"]`: the front window, or one pane of it, saved as a PNG (`UIVerbs.screenshot`).
@objc(FicheroScreenshotCommand)
class FicheroScreenshotCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        guard let path = directParameter as? String, !path.isEmpty else {
            scriptErrorNumber = NSRequiredArgumentsMissingScriptError
            scriptErrorString = "Destination file path is required"
            return nil
        }
        let name = (evaluatedArguments?["pane"] as? String) ?? "window"
        logger.info("AppleScript: screenshot pane '\(name)' -> '\(path)'")
        do {
            return try MainActor.assumeIsolated { () throws -> String in
                let pane: UIPane?
                if name.isEmpty || name.lowercased() == "window" {
                    pane = nil
                } else if let named = UIPane(named: name) {
                    pane = named
                } else {
                    throw UIVerbs.Failure.unknownPane(name)
                }
                return try UIVerbs.screenshot(of: pane, to: path)
            }
        } catch {
            scriptErrorNumber = NSInternalScriptError
            scriptErrorString = error.localizedDescription
            return nil
        }
    }
}
#endif

/// The app drawing its own window into a PNG.
@MainActor
enum FicheroUICapture {
    enum CaptureError: LocalizedError, CustomStringConvertible {
        case noWindow
        case paneNotShown(name: String, shown: [String])
        case renderFailed(String)

        var description: String {
            switch self {
            case .noWindow:
                return "No visible window to capture -- is a project window open?"
            case .paneNotShown(let name, let shown):
                return "The \(name) pane is not shown. Panes shown: \(shown.sorted().joined(separator: ", "))"
            case .renderFailed(let why):
                return "Could not render the capture: \(why)"
            }
        }

        var errorDescription: String? { description }
    }

    /// `pane` of `state`'s window (the whole window when nil) as a PNG at `path`. Answers the absolute path.
    static func capture(pane: UIPane?, of state: WindowState?, to path: String) throws -> String {
        #if os(macOS)
        if pane == .activity {
            // The Activity pane is its own window on the Mac.
            guard let window = NSApp.windows.first(where: {
                $0.isVisible && ($0.identifier?.rawValue.hasPrefix(ActivityWindowSelectionState.monitorWindowID) ?? false)
            }) else { throw CaptureError.paneNotShown(name: "activity", shown: state.map { Array($0.paneFrames.keys) } ?? []) }
            return try write(render(window, crop: nil), to: path)
        }
        guard let window = state?.hostWindow ?? NSApp.keyWindow ?? NSApp.orderedWindows.first(where: \.isVisible)
        else { throw CaptureError.noWindow }
        #else
        guard let window = UIApplication.shared.connectedScenes
            .compactMap({ ($0 as? UIWindowScene)?.keyWindow }).first
        else { throw CaptureError.noWindow }
        #endif
        guard let pane else { return try write(render(window, crop: nil), to: path) }
        guard let frame = state?.paneFrames[pane.frameKey], !frame.isEmpty else {
            throw CaptureError.paneNotShown(name: pane.rawValue, shown: state.map { Array($0.paneFrames.keys) } ?? [])
        }
        return try write(render(window, crop: frame), to: path)
    }

    #if os(macOS)
    /// The window's content, or the `crop` of it (window points, top-left origin), drawn offscreen.
    static func render(_ window: NSWindow, crop: CGRect?) throws -> Data {
        guard let view = window.contentView,
              let rep = view.bitmapImageRepForCachingDisplay(in: view.bounds)
        else { throw CaptureError.renderFailed("no content to draw") }
        view.cacheDisplay(in: view.bounds, to: rep)
        guard var image = rep.cgImage else { throw CaptureError.renderFailed("no bitmap") }
        if let crop {
            let scale = CGFloat(rep.pixelsWide) / max(view.bounds.width, 1)
            let pixels = CGRect(x: crop.minX * scale, y: crop.minY * scale, width: crop.width * scale, height: crop.height * scale)
            guard let cropped = image.cropping(to: pixels.integral) else { throw CaptureError.renderFailed("pane outside the window") }
            image = cropped
        }
        guard let png = NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]) else {
            throw CaptureError.renderFailed("PNG encoding failed")
        }
        return png
    }
    #else
    /// The window, or the `crop` of it (window points), drawn offscreen.
    static func render(_ window: UIWindow, crop: CGRect?) throws -> Data {
        UIGraphicsImageRenderer(bounds: crop ?? window.bounds).pngData { _ in
            window.drawHierarchy(in: window.bounds, afterScreenUpdates: true)
        }
    }
    #endif

    private static func write(_ png: Data, to path: String) throws -> String {
        let url = URL(fileURLWithPath: (path as NSString).expandingTildeInPath)
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try png.write(to: url)
        return url.path
    }
}
