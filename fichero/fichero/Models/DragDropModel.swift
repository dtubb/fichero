import Combine
import Observation
import SwiftUI

/// Model for managing drag and drop state
@MainActor
@Observable
class DragDropModel {
    // MARK: - State Properties
    var isProcessingDrop: Bool = false
    var dropProgress: Double = 0.0
    var dropError: ErrorModel?
    var dropSuccessCount: Int = 0
    var dropFailureCount: Int = 0

    // MARK: - Operation Tracking
    private var activeOperations: Set<UUID> = []

    // MARK: - State Management
    func startProcessing() {
        isProcessingDrop = true
        dropProgress = 0.0
        dropError = nil
        dropSuccessCount = 0
        dropFailureCount = 0
    }

    func endProcessing() {
        isProcessingDrop = false
    }

    func updateProgress(_ progress: Double) {
        dropProgress = progress
    }

    func incrementSuccessCount() {
        dropSuccessCount += 1
    }

    func incrementFailureCount() {
        dropFailureCount += 1
    }

    func setError(_ error: ErrorModel) {
        dropError = error
    }

    func clearError() {
        dropError = nil
    }

    // MARK: - Operation Tracking
    func startOperation() -> UUID {
        let operationId = UUID()
        activeOperations.insert(operationId)
        return operationId
    }

    func endOperation(_ operationId: UUID) {
        activeOperations.remove(operationId)
    }

    func getActiveOperationCount() -> Int {
        return activeOperations.count
    }

    // MARK: - Reset
    func reset() {
        isProcessingDrop = false
        dropProgress = 0.0
        dropError = nil
        dropSuccessCount = 0
        dropFailureCount = 0
        activeOperations.removeAll()
    }
}
