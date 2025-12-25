import SwiftUI
import AppKit

/// Cache model for storing and managing cached UI elements and icons
class CacheModel: ObservableObject {
    
    // MARK: - Icon Cache
    
    /// Cache for system images to avoid repeated creation
    private let iconCache = NSCache<NSString, NSImage>()
    
    /// Get or create a cached system image
    func cachedSystemImage(named name: String, color: Color? = nil) -> Image {
        let cacheKey = "system:\\(name):\(color?.description ?? "default")"
        
        if let cachedImage = iconCache.object(forKey: cacheKey as NSString) {
            return Image(nsImage: cachedImage)
        }
        
        // Create new image
        let systemName = name
        let nsColor = color.map { NSColor($0) } ?? NSColor.systemBlue
        
        let image = NSImage(systemSymbolName: systemName, accessibilityDescription: nil) ?? 
                   NSImage(systemSymbolName: "doc", accessibilityDescription: nil) ?? 
                   NSImage()
        
        // Apply color tint
        if let tintedImage = image.tinted(with: nsColor) {
            iconCache.setObject(tintedImage, forKey: cacheKey as NSString)
            return Image(nsImage: tintedImage)
        }
        
        return Image(nsImage: image)
    }
    
    /// Clear icon cache
    func clearIconCache() {
        iconCache.removeAllObjects()
    }
    
    // MARK: - View Cache
    
    /// Cache for complex view components
    private let viewCache = NSCache<NSString, NSView>()
    
    /// Cache a view component
    func cacheView(_ view: NSView, forKey key: String) {
        viewCache.setObject(view, forKey: key as NSString)
    }
    
    /// Get cached view
    func getCachedView(forKey key: String) -> NSView? {
        return viewCache.object(forKey: key as NSString)
    }
    
    /// Clear view cache
    func clearViewCache() {
        viewCache.removeAllObjects()
    }
    
    // MARK: - Memory Management
    
    init() {
        setupMemoryObservation()
    }
    
    private func setupMemoryObservation() {
        NotificationCenter.default.addObserver(
            forName: NSApplication.didChangeOcclusionStateNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.handleMemoryPressure()
        }
        

    }
    
    private func handleMemoryPressure() {
        // Clear less critical caches first
        viewCache.removeAllObjects()
        
        // Keep icon cache but reduce count
        iconCache.countLimit = max(50, iconCache.countLimit / 2)
    }
    
    deinit {
        NotificationCenter.default.removeObserver(self)
    }
}

// MARK: - NSImage Extension for Tinting

extension NSImage {
    func tinted(with color: NSColor) -> NSImage? {
        guard let tinted = self.copy() as? NSImage else { return nil }
        
        tinted.lockFocus()
        color.set()
        
        let imageRect = NSRect(origin: .zero, size: tinted.size)
        imageRect.fill(using: .sourceAtop)
        
        tinted.unlockFocus()
        
        return tinted
    }
}