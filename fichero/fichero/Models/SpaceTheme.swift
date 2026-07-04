import SwiftUI
#if canImport(RealityKit)
import RealityKit
#endif
#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif

/// Cross-platform colour bridge between the Spatial SwiftUI surfaces and
/// the RealityKit renderer.
///
/// `SwiftUI.Color` is the right type for inspectors and toolbars — but
/// `ModelEntity` materials want `Material.Color`, which is `NSColor` on macOS
/// and `UIColor` on iOS / visionOS. Going through this enum keeps the renderer
/// free of `#if os(...)` and lets the same code paths compile on every Apple
/// platform per the Phase-3 design (see
/// `agent-work/proposals/2026-05-30-spatial-library.md`).
enum SpaceTheme {

    // MARK: - Node colours

    /// SwiftUI colour for a node kind — used by 2D chrome (chips, inspectors).
    static func swiftUIColor(for nodeType: SpatialNodeType) -> Color {
        nodeType.color
    }

    /// SwiftUI colour for a link type — used by 2D chrome.
    static func swiftUIColor(for linkType: LinkType) -> Color {
        linkType.color
    }

    // MARK: - Renderer colours (RealityKit)

    /// Platform-typed colour for a `ModelEntity` material. We return the local
    /// `PlatformColor` alias (which RealityKit's `Material.Color` already
    /// resolves to: `NSColor` on macOS, `UIColor` on iOS / visionOS) rather
    /// than `Material.Color` itself, because SwiftUI ships its own `Material`
    /// type (`.regularMaterial` etc.) and a bare `Material.Color` is ambiguous
    /// in files that import both frameworks.
    static func materialColor(for nodeType: SpatialNodeType, alpha: CGFloat = 1.0) -> PlatformColor {
        platformColor(for: nodeType).withAlphaComponent(alpha)
    }

    static func materialColor(for linkType: LinkType, alpha: CGFloat = 0.7) -> PlatformColor {
        platformColor(for: linkType).withAlphaComponent(alpha)
    }

    // MARK: - Platform colour

    /// Platform colour for a node kind. `NSColor` on macOS, `UIColor`
    /// elsewhere — both expose the same `system*` API the renderer relies on.
    static func platformColor(for nodeType: SpatialNodeType) -> PlatformColor {
        switch nodeType {
        case .source:        return .systemBlue
        case .claim:         return .systemPurple
        case .note:          return .systemOrange
        case .entity:        return .systemGreen
        case .transcription: return .systemTeal
        case .unknown:       return .systemGray
        }
    }

    static func platformColor(for linkType: LinkType) -> PlatformColor {
        switch linkType {
        case .citation:    return .systemBlue
        case .mentions:    return .systemTeal
        case .depicts:     return .systemPink
        case .related:     return .systemGray
        case .contradicts: return .systemRed
        case .supersedes:  return .systemOrange
        case .parentChild: return .systemGray
        case .userDrawn:   return .systemGray
        case .unknown:     return .systemGray
        }
    }

    // MARK: - Background

    /// SwiftUI background colour for the spatial canvas — the closest
    /// cross-platform analogue of macOS's `textBackgroundColor`. Avoids
    /// reaching for AppKit / UIKit from the renderer.
    static var canvasBackground: Color {
        #if os(macOS)
        return Color(nsColor: .textBackgroundColor)
        #else
        return Color(.systemBackground)
        #endif
    }
}

// `PlatformColor` (NSColor / UIColor) is defined in
// `Models/Platform/PlatformAliases.swift` — the canonical home for all
// cross-platform type aliases in Fichero.
