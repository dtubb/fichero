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
/// `PlatformColor` was originally declared alongside the (now-removed) RealityKit
/// spatial theme; it lives here as the canonical cross-platform colour alias.

#if canImport(AppKit)
import AppKit
import SwiftUI

/// `NSColor` on macOS (and Catalyst). Round-trips SwiftUI colours through the
/// AppKit colour APIs any UIKit/AppKit bridge needs.
typealias PlatformColor = NSColor

/// `NSImage` on macOS (and Catalyst). Use `Image(nsImage:)` to lift into SwiftUI.
typealias PlatformImage = NSImage

typealias PlatformFont = NSFont

typealias PlatformViewRepresentable = NSViewRepresentable

/// macOS uses SwiftUI's native split views.
typealias PlatformHSplitView = HSplitView
typealias PlatformVSplitView = VSplitView

extension Color {
    /// Cross-platform bridge: `Color(nsColor:)` on macOS, `Color(uiColor:)` on iOS.
    init(platformColor color: NSColor) { self.init(nsColor: color) }
}

extension NSColor {
    /// Cross-platform name matching UIColor.platformQuaternaryLabel on iOS.
    /// iOS renamed quaternaryLabelColor -> quaternaryLabel; the older name
    /// is unavailable, so callers go through this shim.
    static var platformQuaternaryLabel: NSColor { .quaternaryLabelColor }

    /// Cross-platform name matching UIColor.platformSelectedControl on iOS.
    /// NSColor.selectedControlColor is unavailable on iOS; iOS UIKit has no
    /// direct equivalent so we map to the system selection tint.
    static var platformSelectedControl: NSColor { .selectedControlColor }
}

extension Image {
    /// Cross-platform bridge: `Image(nsImage:)` on macOS, `Image(uiImage:)` on iOS.
    init(platformImage image: NSImage) { self.init(nsImage: image) }
}

#elseif canImport(UIKit)
import SwiftUI
import UIKit

/// `UIColor` on iOS / iPadOS / visionOS.
typealias PlatformColor = UIColor

/// `UIImage` on iOS / iPadOS / visionOS. Use `Image(uiImage:)` to lift into SwiftUI.
typealias PlatformImage = UIImage

typealias PlatformFont = UIFont

typealias PlatformViewRepresentable = UIViewRepresentable

extension Color {
    /// Cross-platform bridge: `Color(nsColor:)` on macOS, `Color(uiColor:)` on iOS.
    init(platformColor color: UIColor) { self.init(uiColor: color) }
}

extension Image {
    /// Cross-platform bridge: `Image(nsImage:)` on macOS, `Image(uiImage:)` on iOS.
    init(platformImage image: UIImage) { self.init(uiImage: image) }
}

// macOS-named semantic color aliases so call sites can write
// `Color(platformColor: .controlBackgroundColor)` cross-platform.
extension UIColor {
    static var controlBackgroundColor: UIColor { .secondarySystemBackground }
    static var textBackgroundColor: UIColor { .systemBackground }
    static var windowBackgroundColor: UIColor { .systemBackground }
    static var separatorColor: UIColor { .separator }

    /// Cross-platform name matching NSColor.quaternaryLabelColor on macOS.
    /// iOS renamed quaternaryLabelColor -> quaternaryLabel; the older name
    /// is unavailable, so callers go through this shim.
    static var platformQuaternaryLabel: UIColor { .quaternaryLabel }

    /// Cross-platform name matching NSColor.selectedControlColor on macOS.
    /// The macOS AppKit highlight tint maps to iOS's tertiary system fill
    /// colour for selection-state surfaces.
    static var platformSelectedControl: UIColor { .tertiarySystemFill }
}

// iOS / iPadOS / visionOS shim: non-draggable stacks that preserve the same
// child-layout order as macOS's HSplitView / VSplitView.
// This is compile-clean; a draggable replacement belongs in the iPad UI pass.
struct PlatformHSplitView<Content: View>: View {
    @ViewBuilder var content: () -> Content
    var body: some View { HStack(spacing: 0, content: content) }
}

struct PlatformVSplitView<Content: View>: View {
    @ViewBuilder var content: () -> Content
    var body: some View { VStack(spacing: 0, content: content) }
}

#endif
