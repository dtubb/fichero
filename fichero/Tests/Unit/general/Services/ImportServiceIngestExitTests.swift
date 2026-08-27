@testable import Fichero
import Foundation
import Testing

// #4232 regression guard: the toolbar status island read `activeIngest`
// forever because the drag-and-drop path calls `importFolderAndWait` directly,
// bypassing `importFolder`'s defer — a finished/failed import left the final
// status published and the island spun at "5/5" while nothing ran. The fix is
// a defer inside `importFolderAndWait` itself; these tests pin the THROW path,
// the one no caller can see succeed and the one the original fix shipped
// without a test for.
@MainActor
@Suite("ImportService.importFolderAndWait clears the published status on every exit (#4232)")
struct ImportServiceIngestExitTests {

    private func service() -> ImportService {
        ImportService(apiClient: APIClient())
    }

    @Test("a thrown start clears activeIngest — even one leaked by a prior run")
    func thrownStartClearsPublishedStatus() async {
        let service = service()
        // Simulate the stuck state the bug shipped: a stale final status is
        // still published when the next import begins.
        service.activeIngest = IngestTaskStatus(
            taskId: "stale",
            status: "completed",
            path: "/tmp/folder",
            progress: nil,
            total: 5,
            processed: 5,
            error: nil,
            documentIds: [],
            failed: 0,
            failures: [],
            filesPerSecond: 0
        )
        service.activeIngestLibraryName = "Stale Library"

        // A folder that cannot exist: startFolderImport must throw before any
        // successful import, exercising the defer's throw path.
        let missing = URL(fileURLWithPath: "/nonexistent/\(UUID().uuidString)")
        await #expect(throws: Error.self) {
            _ = try await service.importFolderAndWait(missing, timeout: 5)
        }

        #expect(service.activeIngest == nil, "a thrown import must not leave a status spinning")
        #expect(service.activeIngestLibraryName == nil)
    }
}
