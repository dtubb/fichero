/// Platform type aliases — one canonical home for every cross-platform
/// `typealias` in Fichero.
///
/// **Why this file?**
/// SwiftUI's own `Color`, `Font`, and `Image` are fully cross-platform and
/// should be preferred everywhere. These aliases are for call sites that must
/// bridge into AppKit / UIKit APIs: RealityKit material colours, NSTextView
/// wrappers, image-editing pipelines, and so on.
///
/// Use `#if canImport(AppKit)` / `#elseif canImport(UIKit)` rather than
/// `#if os(macOS)` so that the same form handles Catalyst and any future
/// Apple platform without extra branches.
///
/// `PlatformColor` was originally declared at the bottom of `MindPalaceTheme.swift`.
/// It now lives here; `MindPalaceTheme.swift` references this canonical location.

#if canImport(AppKit)
import AppKit

/// `NSColor` on macOS (and Catalyst). Used by the RealityKit renderer and any
/// code path that must round-trip through AppKit colour APIs.
typealias PlatformColor = NSColor

/// `NSImage` on macOS (and Catalyst). Use `Image(nsImage:)` to lift into SwiftUI.
typealias PlatformImage = NSImage

/// `NSFont` on macOS (and Catalyst). Use `Font(nsFont:)` / `Font.custom` to
/// work purely in SwiftUI wherever possible.
typealias PlatformFont = NSFont

#elseif canImport(UIKit)
import UIKit

/// `UIColor` on iOS / iPadOS / visionOS.
typealias PlatformColor = UIColor

/// `UIImage` on iOS / iPadOS / visionOS. Use `Image(uiImage:)` to lift into SwiftUI.
typealias PlatformImage = UIImage

/// `UIFont` on iOS / iPadOS / visionOS.
typealias PlatformFont = UIFont

#endif
