import OSLog

// MARK: - Data Loading

extension ActivityProgressView {

    func loadProgressTimeline() async {
        guard let threadId = selectedRun.threadId else { return }

        isLoadingTimeline = true
        defer { isLoadingTimeline = false }

        do {
            let service = ActivityServiceGenerated(apiClient: apiClient)
            _ = try await service.getWorkflowRun(threadId: threadId)

            // Convert progress timeline from dictionary to typed model
            // Note: progressTimeline may not be available in current backend schema
            // TODO: Re-enable when backend schema is updated
            /*
            if let timelineDict = run.progressTimeline {
                let data = try JSONSerialization.data(withJSONObject: timelineDict)
                progressTimeline = try JSONDecoder().decode(ProgressTimeline.self, from: data)
            }
            */
            activityProgressLogger.info("Progress timeline loading disabled - waiting for backend schema update")
        } catch {
            activityProgressLogger.error("Failed to load progress timeline: \(error)")
        }
    }
}
