@testable import Fichero
import XCTest

/// Spec `help.send-logs-to-the-maintainer`: Help › Send Logs to the Maintainer… builds the Save Logs zip, in every
/// tier, after telling the person what is in it. The zip holds logs and about.txt and nothing else.
final class SendLogsToMaintainerTests: XCTestCase {
    private var scratch: URL!

    override func setUpWithError() throws {
        scratch = FileManager.default.temporaryDirectory
            .appendingPathComponent("SendLogsToMaintainerTests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: scratch, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: scratch)
    }

    private func write(_ text: String, to url: URL) throws {
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        try text.write(to: url, atomically: true, encoding: .utf8)
    }

    /// A logs folder with real logs AND the things that must never travel: a library database, a library bundle's
    /// file, a token file and credential files.
    private func logsFolderWithDangerousNeighbours() throws -> URL {
        let logs = scratch.appendingPathComponent("Library/Logs/Fichero", isDirectory: true)
        try write("engine\n", to: logs.appendingPathComponent("engine.log"))
        try write("engine old\n", to: logs.appendingPathComponent("engine.log.1"))
        try write("app\n", to: logs.appendingPathComponent("app.log"))
        try write("crash\n", to: logs.appendingPathComponent("crash/report.log"))
        for secret in ["library.duckdb", "library.duckdb.wal", "app.db", "Marshall.fichero", ".api-key",
                       "bootstrap-token", "credentials.json", "server.pem", "tls.key", "provider-secret.txt"] {
            try write("SECRET", to: logs.appendingPathComponent(secret))
        }
        return logs
    }

    private func relativeFiles(under folder: URL) throws -> [String] {
        let enumerator = try XCTUnwrap(FileManager.default.enumerator(
            at: folder, includingPropertiesForKeys: [.isRegularFileKey], options: [.producesRelativePathURLs]
        ))
        var names: [String] = []
        while let item = enumerator.nextObject() as? URL {
            if try item.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true {
                names.append(item.relativePath)
            }
        }
        return names.sorted()
    }

    /// The collector's output (what is zipped) holds only the logs folder's logs plus about.txt.
    func testTheCollectedFilesAreLogsAndAboutTextOnly() throws {
        let logs = try logsFolderWithDangerousNeighbours()
        let out = scratch.appendingPathComponent("out", isDirectory: true)
        let about = SupportLogs.aboutText(
            version: "2026.10.30", build: "7", tier: "release", osVersion: "Version 27.0", model: "Mac14,2",
            physicalMemory: 8 * 1024 * 1024 * 1024, freeDisk: "100 GB", date: Date(timeIntervalSince1970: 0)
        )
        try SupportLogs.collect(logsDirectory: logs, into: out, about: about)
        XCTAssertEqual(
            try relativeFiles(under: out),
            ["about.txt", "app.log", "crash/report.log", "engine.log", "engine.log.1"]
        )
    }

    /// The real zip: its file list, read with unzip, is the folder's name plus those files and nothing more.
    func testTheZipFileListHoldsNothingOutsideTheLogsAndAboutText() async throws {
        let logs = try logsFolderWithDangerousNeighbours()
        let zip = scratch.appendingPathComponent("Fichero Logs 2026-10-30 10.00.zip")
        try await SupportLogs.makeArchive(at: zip, about: "Fichero x (y)\n", logsDirectory: logs)

        let unzip = Process()
        unzip.executableURL = URL(fileURLWithPath: "/usr/bin/unzip")
        unzip.arguments = ["-Z1", zip.path]
        let pipe = Pipe()
        unzip.standardOutput = pipe
        try unzip.run()
        let data = try pipe.fileHandleForReading.readToEnd() ?? Data()
        unzip.waitUntilExit()
        let entries = String(decoding: data, as: UTF8.self).split(separator: "\n").map(String.init)
            .filter { !$0.hasSuffix("/") }
        let top = "Fichero Logs 2026-10-30 10.00/"
        XCTAssertFalse(entries.isEmpty)
        XCTAssertTrue(entries.allSatisfy { $0.hasPrefix(top) }, "\(entries)")
        XCTAssertEqual(
            entries.map { String($0.dropFirst(top.count)) }.sorted(),
            ["about.txt", "app.log", "crash/report.log", "engine.log", "engine.log.1"]
        )
    }

    /// about.txt names no token and no library path.
    func testAboutTextHasNoTokenAndNoLibraryPath() {
        let about = SupportLogs.currentAbout(tier: "release")
        let lowered = about.lowercased()
        for forbidden in ["token", "secret", "password", "api-key", "bearer", ".duckdb", ".fichero", "/documents/"] {
            XCTAssertFalse(lowered.contains(forbidden), "about.txt mentions \(forbidden)")
        }
    }

    /// about.txt carries no username: the home folder is `~`.
    func testAboutTextPathsCarryNoUsername() throws {
        XCTAssertEqual(
            SupportLogs.anonymisedPath("/Users/" + "jane" + "/Library/Containers/app/Data/Library/Logs/Fichero", home: "/Users/" + "jane" + "/Library/Containers/app/Data"),
            "~/Library/Logs/Fichero"
        )
        XCTAssertEqual(SupportLogs.anonymisedPath("/Users/" + "jane" + "/Library/Logs/Fichero", home: "/elsewhere"), "~/Library/Logs/Fichero")
        // A logs folder UNDER THE HOME (missing is fine: collect says so), so a raw path would carry the username; the
        // temporary directory never does, which is why the earlier form of this test could not fail.
        let logs = URL(fileURLWithPath: NSHomeDirectory())
            .appendingPathComponent("Library/Logs/Fichero-test-\(UUID().uuidString)", isDirectory: true)
        let out = scratch.appendingPathComponent("out", isDirectory: true)
        try SupportLogs.collect(logsDirectory: logs, into: out, about: "Fichero x (y)\n")
        let about = try String(contentsOf: out.appendingPathComponent("about.txt"), encoding: .utf8)
        XCTAssertTrue(about.contains("~/Library/Logs/Fichero-test-"), "the logs folder is written from the home as ~: \(about)")
        XCTAssertFalse(about.contains(NSUserName()), "about.txt names the user: \(about)")
    }

    func testExclusionRules() {
        for name in ["library.duckdb", "x.db", "x.sqlite", "A.fichero", ".api-key", "bootstrap-token", "Credentials.json",
                     "a.pem", "b.key", "my-secret.txt", "Password.txt"] {
            XCTAssertTrue(SupportLogs.isExcluded(fileName: name), name)
        }
        for name in ["engine.log", "engine.log.1", "app.log", "report.log", "about.txt"] {
            XCTAssertFalse(SupportLogs.isExcluded(fileName: name), name)
        }
    }

    /// Offered in every tier, and the draft's To is empty while no address is set (never an invented one).
    @MainActor
    func testTheAddressIsUnsetAndTheConfirmationNamesEveryPart() {
        XCTAssertEqual(SupportLogs.maintainerAddress, "")
        XCTAssertTrue(SupportLogs.maintainerRecipients.isEmpty)
        let text = SupportLogs.contentsDescription
        for part in ["logs folder", "engine log", "about.txt", "libraries", "Nothing is sent"] {
            XCTAssertTrue(text.contains(part), "the confirmation does not say \(part)")
        }
    }
}
