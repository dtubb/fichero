@testable import Fichero
import XCTest

/// Spec `help.save-logs-for-support` (#5656): Help › Save Logs for Support…
/// zips the app's logs folder plus about.txt, dev tier only.
final class SaveLogsForSupportTests: XCTestCase {
    private var scratch: URL!

    override func setUpWithError() throws {
        scratch = FileManager.default.temporaryDirectory
            .appendingPathComponent("SaveLogsForSupportTests-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: scratch, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        try? FileManager.default.removeItem(at: scratch)
    }

    /// engine.log over the cap arrives as its tail (starting on a whole line),
    /// every other log arrives whole, sub-folders are kept, and about.txt
    /// carries the version line and where the logs came from.
    func testCollectCapsEngineLogAndKeepsTheOtherLogs() throws {
        let logs = scratch.appendingPathComponent("Logs/Fichero", isDirectory: true)
        try FileManager.default.createDirectory(
            at: logs.appendingPathComponent("crash", isDirectory: true), withIntermediateDirectories: true
        )
        let engineLines = (1...200).map { String(format: "line %04d engine says something", $0) }
        let engineLog = engineLines.joined(separator: "\n") + "\n"
        try engineLog.write(to: logs.appendingPathComponent("engine.log"), atomically: true, encoding: .utf8)
        try "app log\n".write(to: logs.appendingPathComponent("app.log"), atomically: true, encoding: .utf8)
        try "crash\n".write(
            to: logs.appendingPathComponent("crash/report.log"), atomically: true, encoding: .utf8
        )

        let cap = 1000
        XCTAssertGreaterThan(engineLog.utf8.count, cap, "the fixture must exceed the cap or the test measures nothing")
        let about = SupportLogs.aboutText(
            version: "2026.10.10", build: "42", tier: "dev", osVersion: "Version 27.0",
            model: "Mac14,2", physicalMemory: 8 * 1024 * 1024 * 1024, freeDisk: "100 GB",
            date: Date(timeIntervalSince1970: 0)
        )
        let out = scratch.appendingPathComponent("Fichero Logs 2026-10-10 14.05", isDirectory: true)
        try SupportLogs.collect(logsDirectory: logs, into: out, about: about, engineLogCap: cap)

        let names = try FileManager.default.contentsOfDirectory(atPath: out.path).sorted()
        XCTAssertEqual(names, ["about.txt", "app.log", "crash", "engine.log"])

        let cappedEngine = try String(contentsOf: out.appendingPathComponent("engine.log"), encoding: .utf8)
        let body = cappedEngine.split(separator: "\n", maxSplits: 1).last.map(String.init) ?? ""
        XCTAssertTrue(cappedEngine.hasPrefix("[Fichero: engine.log was \(engineLog.utf8.count) bytes"))
        XCTAssertLessThanOrEqual(body.utf8.count, cap)
        XCTAssertTrue(body.hasPrefix("line "), "the tail starts on a whole line: \(body.prefix(40))")
        XCTAssertTrue(body.hasSuffix("line 0200 engine says something\n"), "the tail keeps the last line")
        XCTAssertFalse(body.contains("line 0001 "), "the head was dropped")

        XCTAssertEqual(try String(contentsOf: out.appendingPathComponent("app.log"), encoding: .utf8), "app log\n")
        XCTAssertEqual(
            try String(contentsOf: out.appendingPathComponent("crash/report.log"), encoding: .utf8), "crash\n"
        )

        let aboutText = try String(contentsOf: out.appendingPathComponent("about.txt"), encoding: .utf8)
        XCTAssertTrue(aboutText.hasPrefix("Fichero 2026.10.10 (42)\n"))
        XCTAssertTrue(aboutText.contains("Feature tier: dev\n"))
        XCTAssertTrue(aboutText.contains("Model: Mac14,2\n"))
        XCTAssertTrue(aboutText.contains("Logs folder: \(logs.path)\n"))
    }

    /// An engine.log under the cap is copied whole, untouched.
    func testCollectCopiesASmallEngineLogWhole() throws {
        let logs = scratch.appendingPathComponent("Logs", isDirectory: true)
        try FileManager.default.createDirectory(at: logs, withIntermediateDirectories: true)
        try "short\n".write(to: logs.appendingPathComponent("engine.log"), atomically: true, encoding: .utf8)
        let out = scratch.appendingPathComponent("out", isDirectory: true)
        try SupportLogs.collect(logsDirectory: logs, into: out, about: "Fichero x (y)\n", engineLogCap: 1000)
        XCTAssertEqual(try String(contentsOf: out.appendingPathComponent("engine.log"), encoding: .utf8), "short\n")
    }

    /// A launch that died before logging still yields about.txt, which says
    /// the logs folder was not there rather than handing over an empty zip.
    func testCollectWithNoLogsFolderStillWritesAboutAndSaysSo() throws {
        let missing = scratch.appendingPathComponent("nope", isDirectory: true)
        let out = scratch.appendingPathComponent("out", isDirectory: true)
        try SupportLogs.collect(logsDirectory: missing, into: out, about: "Fichero x (y)\n")
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath: out.path), ["about.txt"])
        let aboutText = try String(contentsOf: out.appendingPathComponent("about.txt"), encoding: .utf8)
        XCTAssertTrue(aboutText.contains("(not found"))
    }

    func testArchiveNameUsesDotsNotColons() throws {
        var components = DateComponents()
        components.year = 2026; components.month = 10; components.day = 10
        components.hour = 14; components.minute = 5
        let date = try XCTUnwrap(Calendar.current.date(from: components))
        XCTAssertEqual(SupportLogs.archiveBaseName(date: date), "Fichero Logs 2026-10-10 14.05")
    }

    /// Dev tier only.
    func testOfferedInTheDevTierOnly() {
        XCTAssertTrue(SupportLogs.isOffered(for: .dev))
        for tier in [FeatureTier.alpha, .beta, .release] {
            XCTAssertFalse(SupportLogs.isOffered(for: tier), "offered at \(tier)")
        }
    }

    /// The item is in the Help group, behind the tier gate, after the manual link.
    func testHelpMenuMountsTheItemBehindTheTierGate() throws {
        let source = try String(
            contentsOf: AppSource.root().appendingPathComponent("App/Menus/ViewMenuPaneSections.swift"),
            encoding: .utf8
        )
        let help = try XCTUnwrap(source.range(of: "CommandGroup(after: .help) {"), "no Help group")
        let body = String(source[help.upperBound...])
        let manual = try XCTUnwrap(body.range(of: "Link(\"Fichero User Manual\""))
        let gate = try XCTUnwrap(
            body.range(of: "if SupportLogs.isOffered(for: FeatureManager.shared.activeBuildTier) {"),
            "the item is not behind the tier gate"
        )
        let item = try XCTUnwrap(body.range(of: "SaveLogsForSupportButton()"))
        XCTAssertLessThan(manual.lowerBound, gate.lowerBound)
        XCTAssertLessThan(gate.lowerBound, item.lowerBound)

        let button = try String(
            contentsOf: AppSource.root().appendingPathComponent("App/Menus/Help/SaveLogsForSupport.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(button.contains("Button(\"Save Logs for Support…\")"))
    }
}
