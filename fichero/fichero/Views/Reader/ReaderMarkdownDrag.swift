import Foundation
import UniformTypeIdentifiers

// MARK: - What the reader's proxy icon drags (Daniel, 2026-09-01)

/// The reader head's proxy icon promises the TEXT you are reading, as
/// Markdown — not the scan it was read from.
///
/// Dragging the leaf crumb used to hand out `LibraryItemDrag`, whose file
/// representation copies the SOURCE file: drag the reader's proxy icon into a
/// Finder window and you got the page image back. That is the preview pane's
/// answer, not the reader's. The reader is the surface that says what the page
/// SAYS, so its proxy icon promises that.
///
/// Markdown, specifically, because the app already treats a page's content as
/// Markdown everywhere else it renders it — `Representation` maps the
/// `transcription` and `conversion` artifact types to `.markdown`, and the
/// immersive reader hands `pageContent` straight to a Markdown renderer. A
/// `.txt` promise would be the same bytes wearing a less useful name.
enum ReaderMarkdownDrag {
    /// The system's Markdown type, falling back to plain text on a system that
    /// does not declare it. Never `.data`: an untyped promise lands in a
    /// receiving app as an opaque blob rather than as text it can open.
    static var contentType: UTType {
        UTType("net.daringfireball.markdown") ?? .plainText
    }

    /// Sanitised `name.md`. Path separators and colons are stripped rather
    /// than escaped — a document called "1933/34" must not promise a file in
    /// a directory that does not exist.
    static func filename(forDocumentNamed name: String) -> String {
        let cleaned = name
            .components(separatedBy: CharacterSet(charactersIn: "/:\\"))
            .joined(separator: "-")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        let stem = cleaned.isEmpty ? "Document" : cleaned
        return stem.lowercased().hasSuffix(".md") ? stem : "\(stem).md"
    }

    /// An item provider promising `text` under both a Markdown FILE (for
    /// Finder and any editor that takes documents) and plain UTF-8 text (for
    /// anything that takes a string). Returns nil for empty text: a proxy icon
    /// that drags nothing should not be draggable at all.
    ///
    /// `identity` — when supplied — is registered FIRST, under the app's own
    /// `UTType.ficheroDragItem`, so an IN-APP destination gets the node or
    /// artifact ID rather than a wad of Markdown (Daniel, 2026-09-02:
    /// dragging the reader's proxy icon into the workflow bar's "With" slot
    /// must run the workflow on THIS document/artifact). Finder and outside
    /// editors ignore the named flavor and take the file, exactly as before —
    /// registration ORDER is the preference order, so the extension never
    /// changes what a cross-app drop receives.
    static func itemProvider(
        text: String,
        documentName: String,
        identity: LibraryItemDrag? = nil
    ) -> NSItemProvider? {
        guard !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        let name = filename(forDocumentNamed: documentName)
        let data = Data(text.utf8)

        let provider = NSItemProvider()
        provider.suggestedName = name
        if let identity, let json = try? JSONEncoder().encode(identity) {
            provider.registerDataRepresentation(
                // `.all`, not `.ownProcess`: the ownProcess flavor is the one
                // the pasteboard DROPPED in the #4401 multi-drag repro, and
                // an identifier no other app declares is invisible to them
                // regardless. Same choice LibraryItemDrag's own
                // DataRepresentation makes.
                for: .ficheroDragItem, visibility: .all
            ) { completion in
                completion(json, nil)
                return nil
            }
        }
        provider.registerDataRepresentation(
            for: .utf8PlainText, visibility: .all
        ) { completion in
            completion(data, nil)
            return nil
        }
        provider.registerFileRepresentation(
            for: contentType, visibility: .all
        ) { completion in
            // A real file on disk, written on demand: the drop target decides
            // where the copy lands, so writing eagerly at drag START would
            // leave a temp file behind on every drag that goes nowhere.
            let url = FileManager.default.temporaryDirectory
                .appendingPathComponent(UUID().uuidString, isDirectory: true)
                .appendingPathComponent(name)
            do {
                try FileManager.default.createDirectory(
                    at: url.deletingLastPathComponent(), withIntermediateDirectories: true
                )
                try data.write(to: url, options: .atomic)
                // `openInPlace: false` — this is our temp copy, not the
                // document's home; the receiver takes its own.
                completion(url, false, nil)
            } catch {
                completion(nil, false, error)
            }
            return nil
        }
        return provider
    }
}

// MARK: - Reading a Markdown DOCUMENT (Daniel, 2026-09-04)

/// Which documents the reader should render as Markdown rather than as plain
/// text.
///
/// There is no `FileType.markdown`: the engine's text extractor treats `.md`
/// alongside `.txt` and every other text type (`document_loader.py:54`), so
/// the file's own NAME is what distinguishes them. Pure and static so the rule
/// is testable without a document store.
enum ReaderMarkdownDocument {
    /// The extensions that mean Markdown. Deliberately short — `.mdx` and
    /// friends are supersets this renderer does not implement, and claiming
    /// them would render their extra syntax as literal text under a heading
    /// that says "Markdown".
    static let extensions: Set<String> = ["md", "markdown"]

    static func isMarkdown(name: String) -> Bool {
        guard let dot = name.lastIndex(of: ".") else { return false }
        let ext = name[name.index(after: dot)...].lowercased()
        return extensions.contains(String(ext))
    }
}

