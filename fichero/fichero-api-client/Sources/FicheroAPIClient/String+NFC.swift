import Foundation

// MARK: - Unicode NFC normalization (#3076 / #2385)

public extension String {
    /// This string in Unicode **NFC** (canonical precomposed) form.
    ///
    /// macOS filesystem APIs hand back **NFD** (decomposed) Unicode for names
    /// with combining marks — `"Chocó"` comes back as `C h o c o ´` rather than
    /// the precomposed `ó`. The two forms look identical but are different
    /// bytes, so a name that round-trips through `NSSavePanel`, `UserDefaults`,
    /// or the `X-Fichero-Library-Path` header can be stored/compared as a
    /// *second* variant of the same library — the "mojibake" duplicate.
    ///
    /// Normalizing to NFC at every Swift boundary (the value the app *writes* /
    /// *sends*) keeps one canonical path, complementing the backend's own NFC
    /// normalization (#3071) so the app can never create a duplicate variant.
    /// NFC of an already-NFC string is itself, so this is safe to apply anywhere
    /// and idempotent.
    var nfcNormalized: String { precomposedStringWithCanonicalMapping }
}

public extension URL {
    /// This file URL with **only its last path component** NFC-normalized.
    ///
    /// Used when creating a new package (`NSSavePanel` → `saveLibrary`) so the
    /// on-disk name we create is canonical, without touching the user-chosen
    /// (already-existing on disk) parent directory. See ``String/nfcNormalized``.
    var nfcNormalizedLastComponent: URL {
        deletingLastPathComponent()
            .appendingPathComponent(lastPathComponent.nfcNormalized)
    }
}
