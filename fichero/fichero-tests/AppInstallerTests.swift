@testable import Fichero
import XCTest

@MainActor
final class AppInstallerTests: XCTestCase {
    private let sourceURL = URL(fileURLWithPath: "/Users/test/Downloads/Fichero.app")
    private let targetURL = URL(fileURLWithPath: "/Applications/Fichero.app")

    func testPerformMoveCopiesAndRelaunchesWhenTargetMissing() {
        var copiedPairs: [(URL, URL)] = []
        var relaunchedURLs: [URL] = []
        var outcomes: [AppInstaller.MoveOutcome] = []

        let started = AppInstaller.performMove(
            sourceURL: sourceURL,
            targetURL: targetURL,
            dependencies: .init(
                fileExists: { _ in false },
                recycle: { _, _ in XCTFail("recycle should not run without an existing target") },
                copyItem: { sourceURL, targetURL in
                    copiedPairs.append((sourceURL, targetURL))
                },
                relaunchInstalledCopy: { url in
                    relaunchedURLs.append(url)
                    return true
                },
                revealForManualInstall: { _ in XCTFail("manual fallback should not run on success") },
                showManualInstallPrompt: { _, _ in XCTFail("manual fallback should not run on success") }
            ),
            completion: { outcomes.append($0) }
        )

        XCTAssertTrue(started)
        XCTAssertEqual(copiedPairs.count, 1)
        XCTAssertEqual(copiedPairs.first?.0, sourceURL)
        XCTAssertEqual(copiedPairs.first?.1, targetURL)
        XCTAssertEqual(relaunchedURLs, [targetURL])
        XCTAssertEqual(outcomes, [.moved])
    }

    func testPerformMoveRecyclesExistingCopyBeforeCopying() {
        let completionCalled = expectation(description: "completion called")
        var recycledURLs: [URL] = []
        var copiedPairs: [(URL, URL)] = []
        var outcomes: [AppInstaller.MoveOutcome] = []

        let started = AppInstaller.performMove(
            sourceURL: sourceURL,
            targetURL: targetURL,
            dependencies: .init(
                fileExists: { _ in true },
                recycle: { url, completion in
                    recycledURLs.append(url)
                    completion(nil)
                },
                copyItem: { sourceURL, targetURL in
                    copiedPairs.append((sourceURL, targetURL))
                },
                relaunchInstalledCopy: { _ in true },
                revealForManualInstall: { _ in XCTFail("manual fallback should not run on success") },
                showManualInstallPrompt: { _, _ in XCTFail("manual fallback should not run on success") }
            ),
            completion: {
                outcomes.append($0)
                completionCalled.fulfill()
            }
        )

        XCTAssertTrue(started)
        wait(for: [completionCalled], timeout: 1.0)
        XCTAssertEqual(recycledURLs, [targetURL])
        XCTAssertEqual(copiedPairs.count, 1)
        XCTAssertEqual(copiedPairs.first?.0, sourceURL)
        XCTAssertEqual(copiedPairs.first?.1, targetURL)
        XCTAssertEqual(outcomes, [.moved])
    }

    func testPerformMoveFallsBackToManualDragWhenRecycleDenied() {
        let completionCalled = expectation(description: "completion called")
        var revealedURLs: [URL] = []
        var promptedReasons: [String] = []
        var outcomes: [AppInstaller.MoveOutcome] = []

        struct FakeDeniedError: LocalizedError {
            var errorDescription: String? { "not allowed" }
        }

        let started = AppInstaller.performMove(
            sourceURL: sourceURL,
            targetURL: targetURL,
            dependencies: .init(
                fileExists: { _ in true },
                recycle: { _, completion in
                    completion(FakeDeniedError())
                },
                copyItem: { _, _ in XCTFail("copy should not run when recycle is denied") },
                relaunchInstalledCopy: { _ in XCTFail("relaunch should not run when recycle is denied"); return false },
                revealForManualInstall: { revealedURLs.append($0) },
                showManualInstallPrompt: { _, reason in promptedReasons.append(reason) }
            ),
            completion: {
                outcomes.append($0)
                completionCalled.fulfill()
            }
        )

        XCTAssertTrue(started)
        wait(for: [completionCalled], timeout: 1.0)
        XCTAssertEqual(revealedURLs, [sourceURL])
        XCTAssertEqual(promptedReasons, [AppInstaller.manualInstallMessage])
        XCTAssertEqual(outcomes, [.needsManualDrag(reason: AppInstaller.manualInstallMessage)])
    }
}
