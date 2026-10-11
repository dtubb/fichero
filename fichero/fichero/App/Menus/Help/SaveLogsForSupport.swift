#if canImport(AppKit)
import AppKit
#endif
import Foundation
import SwiftUI
import UniformTypeIdentifiers

/// Help › Save Logs for Support… (#5656, spec `help.save-logs-for-support`).
///
/// A tester whose app crashes on launch could only hand over its logs with a
/// Terminal command. This item writes one zip of everything under the app's
/// `Library/Logs/Fichero` plus an `about.txt`, through a save panel.
///
/// APP-SIDE BY DESIGN — a deliberate exception to "logic in the engine": it is
/// needed exactly when the engine is NOT running (it failed to launch, or it
/// crashed), so it cannot depend on the engine. It reads only files and system
/// facts the app itself can see.
///
/// `nonisolated`: the target's default isolation is MainActor, and copying a
/// 20 MB log and zipping it must not run there. Only `makeArchive` leaves the
/// main actor (`@concurrent`); the rest are plain functions the tests call.
nonisolated enum SupportLogs {
    /// engine.log can grow without bound; the zip carries only its last 20 MB.
    static let engineLogCap = 20 * 1024 * 1024

    /// Dev tier only (#5656): a support tool for testers, not a release feature.
    /// MainActor because `FeatureTier` is (the target's default isolation).
    @MainActor static func isOffered(for tier: FeatureTier) -> Bool { tier == .dev }

    /// The logs folder as the sandboxed app sees it. `.libraryDirectory` is
    /// container-relative under the App Sandbox, so this is
    /// `<container>/Data/Library/Logs/Fichero` — the same folder
    /// `EmbeddedBackendService.engineLogURL` writes engine.log into.
    static var logsDirectory: URL {
        FileManager.default
            .urls(for: .libraryDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Logs/Fichero", isDirectory: true)
    }

    /// `Fichero Logs 2026-10-10 14.05` — dots, not colons: a colon is a path
    /// separator to Finder.
    static func archiveBaseName(date: Date) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd HH.mm"
        return "Fichero Logs \(formatter.string(from: date))"
    }

    // MARK: - The folder's contents (pure; tested)

    /// Builds the folder the zip is made from: every file under `logsDirectory`
    /// (sub-folders kept), with a top-level engine.log larger than `engineLogCap`
    /// copied as its tail, plus `about.txt`. A missing logs folder is not an
    /// error — a first launch that died early may never have made one — but
    /// about.txt says so, so the reader knows the zip is not just empty.
    static func collect(
        logsDirectory: URL,
        into destination: URL,
        about: String,
        engineLogCap: Int = engineLogCap
    ) throws {
        let fileManager = FileManager.default
        try fileManager.createDirectory(at: destination, withIntermediateDirectories: true)

        var logsNote = "Logs folder: \(logsDirectory.path)"
        if fileManager.fileExists(atPath: logsDirectory.path) {
            var enumerationError: Error?
            let keys: [URLResourceKey] = [.isRegularFileKey, .fileSizeKey]
            let enumerator = fileManager.enumerator(
                at: logsDirectory,
                includingPropertiesForKeys: keys,
                options: [.producesRelativePathURLs],
                errorHandler: { _, error in
                    enumerationError = error
                    return false
                }
            )
            while let item = enumerator?.nextObject() as? URL {
                let values = try item.resourceValues(forKeys: Set(keys))
                guard values.isRegularFile == true else { continue }
                let relativePath = item.relativePath
                let target = destination.appendingPathComponent(relativePath)
                try fileManager.createDirectory(
                    at: target.deletingLastPathComponent(), withIntermediateDirectories: true
                )
                let size = values.fileSize ?? 0
                if relativePath == "engine.log", size > engineLogCap {
                    try copyTail(of: item, to: target, size: size, cap: engineLogCap)
                } else {
                    try fileManager.copyItem(at: item, to: target)
                }
            }
            if let enumerationError { throw enumerationError }
        } else {
            logsNote += " (not found — nothing was logged there)"
        }

        let text = about + logsNote + "\n"
        try text.write(to: destination.appendingPathComponent("about.txt"), atomically: true, encoding: .utf8)
    }

    /// Copies the last `cap` bytes of `source`, starting at the first whole
    /// line, so the file opens on a complete log line. Reads only the tail —
    /// never the whole multi-GB file.
    static func copyTail(of source: URL, to target: URL, size: Int, cap: Int) throws {
        let handle = try FileHandle(forReadingFrom: source)
        defer { try? handle.close() }
        try handle.seek(toOffset: UInt64(size - cap))
        var tail = try handle.readToEnd() ?? Data()
        if let newline = tail.firstIndex(of: 0x0A) {
            tail = tail[tail.index(after: newline)...]
        }
        let header = "[Fichero: engine.log was \(size) bytes; this is its last \(tail.count)]\n"
        try (Data(header.utf8) + tail).write(to: target)
    }

    /// The facts a support reader asks first. Inputs are passed in so the test
    /// can pin the text; `currentAbout(tier:)` supplies the live values.
    static func aboutText(
        version: String,
        build: String,
        tier: String,
        osVersion: String,
        model: String,
        physicalMemory: UInt64,
        freeDisk: String,
        date: Date
    ) -> String {
        let memory = ByteCountFormatter.string(fromByteCount: Int64(physicalMemory), countStyle: .memory)
        return """
        Fichero \(version) (\(build))
        Feature tier: \(tier)
        macOS: \(osVersion)
        Model: \(model)
        Memory: \(memory)
        Free disk: \(freeDisk)
        Date: \(ISO8601DateFormatter().string(from: date))

        """
    }

    /// `tier` is `FeatureTier.environmentValue`, read on the main actor by the caller.
    static func currentAbout(tier: String, date: Date = Date()) -> String {
        let info = Bundle.main.infoDictionary ?? [:]
        return aboutText(
            version: info["CFBundleShortVersionString"] as? String ?? "unknown",
            build: info["CFBundleVersion"] as? String ?? "unknown",
            tier: tier,
            osVersion: ProcessInfo.processInfo.operatingSystemVersionString,
            model: modelIdentifier(),
            physicalMemory: ProcessInfo.processInfo.physicalMemory,
            freeDisk: freeDiskDescription(),
            date: date
        )
    }

    /// `hw.model`, e.g. `Mac14,2`.
    static func modelIdentifier() -> String {
        var size = 0
        guard sysctlbyname("hw.model", nil, &size, nil, 0) == 0, size > 0 else { return "unknown" }
        var bytes = [CChar](repeating: 0, count: size)
        guard sysctlbyname("hw.model", &bytes, &size, nil, 0) == 0 else { return "unknown" }
        let utf8 = bytes.prefix { $0 != 0 }.map { UInt8(bitPattern: $0) }
        return String(decoding: utf8, as: UTF8.self)
    }

    static func freeDiskDescription() -> String {
        do {
            let values = try URL(fileURLWithPath: NSHomeDirectory())
                .resourceValues(forKeys: [.volumeAvailableCapacityForImportantUsageKey])
            guard let bytes = values.volumeAvailableCapacityForImportantUsage else { return "unknown" }
            return ByteCountFormatter.string(fromByteCount: bytes, countStyle: .file)
        } catch {
            return "unknown (\(error.localizedDescription))"
        }
    }

    // MARK: - The zip

    /// Collects into a temporary folder, zips it with the system's own
    /// NSFileCoordinator `.forUploading` (it hands back a zip of a directory),
    /// and copies that zip to `destination`, replacing a file the save panel
    /// already confirmed overwriting.
    @concurrent
    static func makeArchive(at destination: URL, about: String) async throws {
        let fileManager = FileManager.default
        let scratch = fileManager.temporaryDirectory
            .appendingPathComponent("SupportLogs-\(UUID().uuidString)", isDirectory: true)
        defer { try? fileManager.removeItem(at: scratch) }
        let folder = scratch.appendingPathComponent(
            destination.deletingPathExtension().lastPathComponent, isDirectory: true
        )
        try collect(logsDirectory: logsDirectory, into: folder, about: about)

        var coordinatorError: NSError?
        var copyError: Error?
        NSFileCoordinator().coordinate(
            readingItemAt: folder, options: .forUploading, error: &coordinatorError
        ) { zipURL in
            // `zipURL` is only valid inside this block.
            do {
                if fileManager.fileExists(atPath: destination.path) {
                    try fileManager.removeItem(at: destination)
                }
                try fileManager.copyItem(at: zipURL, to: destination)
            } catch {
                copyError = error
            }
        }
        if let coordinatorError { throw coordinatorError }
        if let copyError { throw copyError }
    }
}

// MARK: - The menu item

#if os(macOS)
/// Help › Save Logs for Support… — save panel on the Desktop, zip, reveal.
struct SaveLogsForSupportButton: View {
    var body: some View {
        Button("Save Logs for Support…") {
            Task { await Self.run() }
        }
    }

    static func run() async {
        let tier = FeatureManager.shared.activeBuildTier.environmentValue
        let name = SupportLogs.archiveBaseName(date: Date()) + ".zip"
        guard let url = await savePanel(suggestedName: name) else { return }
        do {
            try await SupportLogs.makeArchive(at: url, about: SupportLogs.currentAbout(tier: tier))
            ExportPresentation.revealInFinder(url)
        } catch {
            ExportPresentation.showError(error, title: "Couldn’t Save the Logs")
        }
    }

    /// Desktop as the starting folder; the panel's choice is what the sandbox
    /// lets the app write.
    private static func savePanel(suggestedName: String) async -> URL? {
        await withCheckedContinuation { continuation in
            let panel = NSSavePanel()
            panel.nameFieldStringValue = suggestedName
            panel.directoryURL = FileManager.default.urls(for: .desktopDirectory, in: .userDomainMask).first
            panel.allowedContentTypes = [.zip]
            panel.canCreateDirectories = true
            panel.begin { result in
                continuation.resume(returning: result == .OK ? panel.url : nil)
            }
        }
    }
}
#endif
