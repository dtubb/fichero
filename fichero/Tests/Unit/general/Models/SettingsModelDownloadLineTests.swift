//
//  SettingsModelDownloadLineTests.swift
//  FicheroTests
//
//  `activity.window.one-surface`, the downloads half: Settings' line under a model says what the model's
//  `download-model` job says (its reason, or "Downloading <name>…" when it has none) and keeps no count of its
//  own: the job's done and total never reach the line. Through the real `ModelDownloads` and the generated client;
//  only the transport is stubbed. Not covered: the SwiftUI line (`SettingsModelDownloadLine`) only reads `line(_:)`.
//

@testable import Fichero
import FicheroAPIClient
import XCTest

@MainActor
final class SettingsModelDownloadLineTests: XCTestCase {
    private typealias Stub = ActivityStubbedResponse

    private static let key = ModelDownloads.Key(runtime: "mlx", model: "Qwen2.5-VL-7B")

    override func setUp() {
        super.setUp()
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
        ActivityMockTransport.reset([])
    }

    private func downloads() -> ModelDownloads {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ActivityMockTransport.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/SettingsModelDownloadLineTests.fichero",
            session: URLSession(configuration: configuration)
        )
        return ModelDownloads(client: client, followInterval: .seconds(3600))
    }

    private static func job(state: String, reason: String?, done: Int, total: Int) -> Stub {
        let said = reason.map { ",\"reason\":\"\($0)\"" } ?? ""
        return Stub(pathSuffix: "/api/activity/jobs/dl-1", method: "GET", status: 200, body: Data("""
        {"id":"dl-1","kind":"download-model","name":"Download a model","subject":"mlx:Qwen2.5-VL-7B",
         "state":"\(state)"\(said),"done":\(done),"total":\(total)}
        """.utf8))
    }

    private static let queued = Stub(
        pathSuffix: "/api/local-models/download/mlx/Qwen2.5-VL-7B", method: "POST", status: 200,
        body: Data(#"{"status":"queued","model_type":"mlx","model_id":"Qwen2.5-VL-7B","job_id":"dl-1"}"#.utf8))

    func testTheLineSaysTheJobsWordsAndKeepsNoCountOfItsOwn() async throws {
        // WHY: Settings' bars once kept their own progress list. The line is the job's reason as served, and a job's
        // done and total (3 of 10 here) are not turned into a count the job did not say.
        let downloads = downloads()
        ActivityMockTransport.reset([Self.queued])
        await downloads.start(Self.key, name: "Qwen2.5-VL 7B")

        ActivityMockTransport.reset([Self.job(state: "running", reason: "Downloading Qwen: 1.2 GB of 5.6 GB", done: 3, total: 10)])
        _ = await downloads.refresh(Self.key)
        XCTAssertEqual(downloads.line(Self.key), "Downloading Qwen: 1.2 GB of 5.6 GB", "the job's words, as served")

        ActivityMockTransport.reset([Self.job(state: "running", reason: nil, done: 4, total: 10)])
        _ = await downloads.refresh(Self.key)
        XCTAssertEqual(downloads.line(Self.key), "Downloading Qwen2.5-VL 7B…", "no reason: no count is made up from 4 of 10")

        ActivityMockTransport.reset([Self.job(state: "failed", reason: "the MLX runtime is not set up", done: 4, total: 10)])
        _ = await downloads.refresh(Self.key)
        XCTAssertEqual(downloads.line(Self.key), "Could not download Qwen2.5-VL 7B: the MLX runtime is not set up")

        ActivityMockTransport.reset([Self.job(state: "done", reason: nil, done: 10, total: 10)])
        _ = await downloads.refresh(Self.key)
        XCTAssertNil(downloads.line(Self.key), "a finished job leaves no line")
    }
}
