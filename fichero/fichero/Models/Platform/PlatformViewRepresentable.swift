/// Cross-platform `ViewRepresentable` aliases.
///
/// **Why this file?**
/// SwiftUI splits its native-view bridging protocol into
/// `NSViewRepresentable` (macOS / Catalyst) and `UIViewRepresentable`
/// (iOS / iPadOS / visionOS). A struct that conforms to one won't compile
/// on the other platform without `#if` guards scattered across the file.
///
/// Declare `PlatformViewRepresentable` here once; conforming structs can use
/// the alias and stay `#if`-free in their own bodies. The compiler picks the
/// right protocol at build time.
///
/// **Usage**
/// ```swift
/// struct MyNativeView: PlatformViewRepresentable {
///     #if canImport(AppKit)
///     func makeNSView(context: Context) -> NSScrollView { … }
///     func updateNSView(_ view: NSScrollView, context: Context) { … }
///     #elseif canImport(UIKit)
///     func makeUIView(context: Context) -> UIScrollView { … }
///     func updateUIView(_ view: UIScrollView, context: Context) { … }
///     #endif
/// }
/// ```
///
/// The `make*/update*` methods are still platform-specific because AppKit and
/// UIKit views don't share a common superclass here. Gate them with
/// `#if canImport(AppKit)` / `#elseif canImport(UIKit)` inside the conforming type.

import SwiftUI

#if canImport(AppKit)
/// `NSViewRepresentable` on macOS / Catalyst.
typealias PlatformViewRepresentable = NSViewRepresentable

/// `NSViewControllerRepresentable` on macOS / Catalyst.
typealias PlatformViewControllerRepresentable = NSViewControllerRepresentable

#elseif canImport(UIKit)
/// `UIViewRepresentable` on iOS / iPadOS / visionOS.
typealias PlatformViewRepresentable = UIViewRepresentable

/// `UIViewControllerRepresentable` on iOS / iPadOS / visionOS.
typealias PlatformViewControllerRepresentable = UIViewControllerRepresentable

#endif
