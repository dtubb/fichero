/// Cross-platform pasteboard / clipboard wrapper.
///
/// **Why this file?**
/// macOS uses `NSPasteboard` (general pasteboard, `NSPasteboard.general`);
/// iOS / iPadOS uses `UIPasteboard` (`.general` singleton). The surface area
/// required by Fichero today is tiny — read and write plain strings — so this
/// wrapper exposes exactly that and nothing more.
///
/// Extend this type with additional UTI flavours (RTF, URL, image) only when a
/// concrete call site needs them (YAGNI). Do NOT reach into `NSPasteboard` or
/// `UIPasteboard` directly from view code; always go through this type so that
/// the iOS port doesn't need scattered `#if os(macOS)` blocks.
///
/// **Usage**
/// ```swift
/// PlatformPasteboard.writeString("Hello, world!")
/// let text = PlatformPasteboard.string() // → "Hello, world!"
/// ```

#if canImport(AppKit)
import AppKit

/// Thin clipboard wrapper over `NSPasteboard.general`.
enum PlatformPasteboard {

    /// Write `string` to the system clipboard, replacing its current contents.
    static func writeString(_ string: String) {
        let pasteboard = NSPasteboard.general
        pasteboard.clearContents()
        pasteboard.setString(string, forType: .string)
    }

    /// Return the first plain-text item on the system clipboard, or `nil` if
    /// the clipboard is empty or contains no plain text.
    static func string() -> String? {
        NSPasteboard.general.string(forType: .string)
    }
}

#elseif canImport(UIKit)
import UIKit

/// Thin clipboard wrapper over `UIPasteboard.general`.
enum PlatformPasteboard {

    /// Write `string` to the system clipboard, replacing its current contents.
    static func writeString(_ string: String) {
        UIPasteboard.general.string = string
    }

    /// Return the current plain-text clipboard contents, or `nil` if the
    /// clipboard is empty or contains no plain text.
    static func string() -> String? {
        UIPasteboard.general.string
    }
}

#endif
