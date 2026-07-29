#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif
import SwiftUI

extension BackendConnectionView {
    /// Engine icon resolved from the bundled Fichero Server.app.
    /// Falls back to the system server icon if the engine icon isn't found.
    var engineIconImage: PlatformImage {
        if let resourcePath = Bundle.main.resourcePath {
            // Briefcase names the icon after the app name — `server` since #4227.
            let iconPath = "\(resourcePath)/Fichero Server.app/Contents/Resources/server.icns"
            if let image = PlatformImage(contentsOfFile: iconPath) {
                return image
            }
        }
        #if canImport(AppKit)
        return PlatformImage(systemSymbolName: "server.rack", accessibilityDescription: nil) ?? PlatformImage()
        #elseif canImport(UIKit)
        return PlatformImage(systemName: "server.rack") ?? PlatformImage()
        #else
        return PlatformImage()
        #endif
    }

    /// Fichero app icon loaded as a flat .icns from the app bundle, NOT
    /// via NSApp.applicationIconImage which on macOS Tahoe (26+) gets
    /// auto-wrapped in the system rounded-squircle treatment. The engine
    /// icon next to it renders flat (loaded the same way), so loading
    /// the Fichero side flat keeps the splash visually consistent (#793).
    var ficheroIconImage: PlatformImage {
        if let resourcePath = Bundle.main.resourcePath {
            // The app's compiled icon catalog produces AppIcon.icns at
            // the bundle root. Loading it directly via PlatformImage avoids
            // the system squircle that NSApp.applicationIconImage applies.
            let iconPath = "\(resourcePath)/AppIcon.icns"
            if let image = PlatformImage(contentsOfFile: iconPath) {
                return image
            }
        }
        // Fallback to the Tahoe-treated app icon if the .icns isn't
        // findable (custom builds, dev sandbox).
        #if canImport(AppKit)
        return NSApp.applicationIconImage ?? PlatformImage()
        #elseif canImport(UIKit)
        return PlatformImage(systemName: "books.vertical") ?? PlatformImage()
        #else
        return PlatformImage()
        #endif
    }
}
