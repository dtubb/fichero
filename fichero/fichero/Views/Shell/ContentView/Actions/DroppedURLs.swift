import Foundation
/// What a drop of URLs turned out to contain (#2386).
///
/// A named type rather than a 3-tuple: the third bucket — remote URLs we
/// recognise and refuse — is the whole point of the split, and a tuple member
/// called `.2` is exactly how a caller forgets it exists.
struct DroppedURLs {
    /// Delete the `fichero-drop-UUID` directories an external drop staged
    /// (#4459). Best-effort: a directory the OS already reaped is not an
    /// error, and failing an import because its scratch space could not be
    /// tidied would be the tail wagging the dog.
    ///
    /// Only `fichero-drop-` — INBOUND staging, ours to delete. The outbound
    /// `fichero-drag-` export belongs to the Finder and must never be swept
    /// from under a copy in progress.
    static func removeTemporaryDirectories(_ directories: [URL]) {
        for directory in directories {
            try? FileManager.default.removeItem(at: directory)
        }
    }

    /// Fichero library packages to open in a window.
    let libraryURLs: [URL]
    /// Files on disk to hand to the importer.
    let importURLs: [URL]
    /// Not on disk — an http(s) link from a browser, or a scheme with no story.
    /// Refused with an explanation rather than passed to the importer as a path.
    let remoteURLs: [URL]

    /// Split dropped URLs into libraries to open, files to import, and REMOTE
    /// urls we cannot import yet (#2386).
    ///
    /// The third bucket is the point. There was no scheme check at all: every
    /// non-library URL went into `importURLs`, so dragging a link from a
    /// browser handed `https://example.org/paper.pdf` to the importer AS A FILE
    /// PATH. The importer then failed on a path that does not exist, and the
    /// user saw a drop that did nothing.
    ///
    /// Downloading it is a real feature with its own failure surface —
    /// redirects, auth walls, content-type sniffing, a partial file on a
    /// dropped connection — and is NOT built here. What is built here is
    /// honesty: a remote URL is recognised as remote and SAID SO, instead of
    /// being mistaken for a file. A drop that explains itself is a smaller lie
    /// than a drop that silently does nothing, which is what #2386 reports.
    ///
    /// Telling the user is `ContentView.reportRefusedRemoteURLs`, not this type:
    /// it needs the view's `importError` and logger, and this type stays free of
    /// both so it can be tested without a window.
    ///
    /// `static` and pure so the three-way split can be tested without a window,
    /// a drag session or an engine. The bug it now guards against was invisible
    /// precisely because nothing could ask it a question.
    static func classify(_ urls: [URL]) -> DroppedURLs {
        var libraryURLs: [URL] = []
        var importURLs: [URL] = []
        var remoteURLs: [URL] = []

        for url in urls {
            if url.isFileURL == false {
                // Anything not on disk: http(s) from a browser link, and also
                // schemes we have no story for at all. Bucketed by what the URL
                // IS rather than by a scheme allowlist, so a `mailto:` or a
                // custom scheme cannot fall through to the importer either.
                remoteURLs.append(url)
            } else if url.isFicheroLibraryPackage {
                libraryURLs.append(url.standardizedFileURL)
            } else {
                importURLs.append(url)
            }
        }

        return DroppedURLs(
            libraryURLs: libraryURLs,
            importURLs: importURLs,
            remoteURLs: remoteURLs
        )
    }
}
