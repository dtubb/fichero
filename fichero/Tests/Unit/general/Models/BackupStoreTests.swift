@testable import Fichero
import FicheroAPIClient
import Testing

@MainActor
@Suite("BackupStore")
struct BackupStoreTests {

    @Test("create refuses to issue a snapshot request when no library is open")
    func createRequiresLibraryPath() async {
        let store = BackupStore(client: FicheroClient(libraryPath: nil))

        let created = await store.create(reason: "before migration")

        #expect(!created)
        #expect(store.statusMessage == "No library open")
        #expect(!store.isCreating)
        #expect(store.snapshots.isEmpty)
    }
}
