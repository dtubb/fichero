import SwiftUI
import UniformTypeIdentifiers
import Combine

/// Service for handling drag and drop operations with proper synchronization and error handling
@MainActor
class DragDropService: ObservableObject {
    // MARK: - Dependencies
    weak var documentStore: DocumentStore?
    weak var errorService: ErrorService?
    weak var performanceService: PerformanceService?

    // MARK: - State
    let dragDropModel: DragDropModel
    private var benchmark: PerformanceBenchmark?

    // MARK: - Initialization
    init(dragDropModel: DragDropModel) {
        self.dragDropModel = dragDropModel
    }

    // MARK: - Dependency Injection
    func injectDependencies(
        documentStore: DocumentStore,
        errorService: ErrorService,
        performanceService: PerformanceService
    ) {
        self.documentStore = documentStore
        self.errorService = errorService
        self.performanceService = performanceService
    }

    // MARK: - Chat Drop Handling
    func handleChatDrop(providers: [NSItemProvider], completion: @escaping @Sendable ([String]) -> Void) {
        dragDropModel.startProcessing()
        self.benchmark = performanceService?.startBenchmark("chat_drop")

        let documentIds = ThreadSafeArray<String>()
        let operationCount = providers.count

        // Track completed operations
        let completedOperations = AtomicInt(value: 0)

        for provider in providers {
            let operationId = dragDropModel.startOperation()

            // Use weak self to avoid retain cycles
            provider.loadItem(forTypeIdentifier: UTType.text.identifier, options: nil) { [weak self] data, error in
                guard let self = self else { return }

                defer {
                    let completed = completedOperations.incrementAndGet()

                    // Update progress on main actor
                    Task { @MainActor in
                        self.dragDropModel.endOperation(operationId)
                        self.dragDropModel.updateProgress(Double(completed) / Double(operationCount))

                        // Check if all operations are complete
                        if completed == operationCount {
                            self.dragDropModel.endProcessing()
                            self.benchmark?.end()

                            let ids = await documentIds.getAll()
                            if !ids.isEmpty {
                                completion(ids)
                            }
                        }
                    }
                }

                if let error = error {
                    Task { @MainActor in
                        self.handleProviderError(error, providerType: "text")
                    }
                    return
                }

                guard let data = data as? Data else {
                    Task { @MainActor in
                        self.handleInvalidDataError(providerType: "text")
                    }
                    return
                }

                guard let docId = String(data: data, encoding: .utf8) else {
                    Task { @MainActor in
                        self.handleDecodingError(providerType: "text")
                    }
                    return
                }

                // Thread-safe append
                Task { @MainActor in
                    await documentIds.append(docId)
                }
            }

            // Also check for plain text type
            provider.loadItem(forTypeIdentifier: UTType.plainText.identifier, options: nil) { [weak self] data, error in
                guard let self = self else { return }

                defer {
                    let completed = completedOperations.incrementAndGet()

                    // Update progress on main actor
                    Task { @MainActor in
                        self.dragDropModel.endOperation(operationId)
                        self.dragDropModel.updateProgress(Double(completed) / Double(operationCount))

                        // Check if all operations are complete
                        if completed == operationCount {
                            self.dragDropModel.endProcessing()
                            self.benchmark?.end()

                            let ids = await documentIds.getAll()
                            if !ids.isEmpty {
                                completion(ids)
                            }
                        }
                    }
                }

                if let error = error {
                    Task { @MainActor in
                        self.handleProviderError(error, providerType: "plainText")
                    }
                    return
                }

                guard let data = data as? Data else {
                    Task { @MainActor in
                        self.handleInvalidDataError(providerType: "plainText")
                    }
                    return
                }

                guard let docId = String(data: data, encoding: .utf8) else {
                    Task { @MainActor in
                        self.handleDecodingError(providerType: "plainText")
                    }
                    return
                }

                // Thread-safe append
                Task { @MainActor in
                    await documentIds.append(docId)
                }
            }
        }
    }

    // MARK: - Library Drop Handling
    func handleLibrarySectionDrop(providers: [NSItemProvider], completion: @escaping @Sendable (Bool) -> Void) {
        self.benchmark = performanceService?.startBenchmark("library_drop")
        let benchmark = performanceService?.startBenchmark("library_drop")
        let handled = ThreadSafeValue<Bool>(false)
        let operationCount = providers.count
        let completedOperations = AtomicInt(value: 0)

        for provider in providers where provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
            let operationId = dragDropModel.startOperation()

            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { [weak self] (urlData, error) in
                guard let self = self else { return }

                defer {
                    let completed = completedOperations.incrementAndGet()

                    // Update progress on main actor
                    Task { @MainActor in
                        self.dragDropModel.endOperation(operationId)
                        self.dragDropModel.updateProgress(Double(completed) / Double(operationCount))

                        // Check if all operations are complete
                        if completed == operationCount {
                            self.dragDropModel.endProcessing()
                            self.benchmark?.end()
                            let wasHandled = await handled.get()
                            completion(wasHandled)
                        }
                    }
                }

                if let error = error {
                    Task { @MainActor in
                        self.handleProviderError(error, providerType: "fileURL")
                    }
                    return
                }

                guard let urlData = urlData as? Data else {
                    Task { @MainActor in
                        self.handleInvalidDataError(providerType: "fileURL")
                    }
                    return
                }

                guard let url = URL(dataRepresentation: urlData, relativeTo: nil) else {
                    Task { @MainActor in
                        self.handleInvalidURLError()
                    }
                    return
                }

                // Handle the file drop
                Task { @MainActor in
                    self.handleFileDropOnLibrary(url: url) { @MainActor success in
                        if success {
                            Task { @MainActor in
                                await handled.set(true)
                            }
                            self.dragDropModel.incrementSuccessCount()
                        } else {
                            self.dragDropModel.incrementFailureCount()
                        }
                    }
                }
            }
        }

        // If no providers were processed, complete immediately
        if providers.isEmpty {
            dragDropModel.endProcessing()
            benchmark?.end()
            completion(false)
        }
    }

    // MARK: - File Drop Handling
    @MainActor
    private func handleFileDropOnLibrary(url: URL, completion: @escaping @MainActor @Sendable (Bool) -> Void) {

        Task { @MainActor in
            do {
                // Import file as a top-level document (no parent)
                if let importedDoc = try await documentStore?.importFile(at: url, parentId: nil) {

                    // Show success feedback
                    showImportSuccessAlert(documentName: importedDoc.name)
                    completion(true)
                    return
                }

                completion(false)
            } catch {
                let errorModel = ErrorModel.fileSystemError(
                    message: "Failed to import file: \((error.localizedDescription))",
                    context: [
                        "operation": "file_import",
                        "file_path": url.path,
                        "file_name": url.lastPathComponent
                    ],
                    isRecoverable: true
                )
                errorService?.reportError(errorModel)

                // Show error feedback
                showImportErrorAlert(error: error.localizedDescription)
                completion(false)
            }
        }
    }

}
