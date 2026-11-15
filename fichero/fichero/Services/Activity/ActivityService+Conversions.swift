import FicheroAPIClient
import Foundation
import OpenAPIRuntime

// Split out of ActivityService.swift by file_length (#6101); behaviour unchanged.

// MARK: - Type Conversions

extension ActivityService {
    /// Convert generated ActivityResponse to app ActivityItem
    func convertToActivityItem(_ response: Components.Schemas.ActivityResponse) -> ActivityItem {
        // Convert metadata from OpenAPIObjectContainer to [String: AnyValueAsString]
        var metadata: [String: AnyValueAsString]?
        if let metadataPayload = response.metadata {
            var converted: [String: AnyValueAsString] = [:]
            for (key, value) in metadataPayload.additionalProperties.value {
                // Convert any value to string representation
                let stringValue: String
                if let str = value as? String {
                    stringValue = str
                } else if let bool = value as? Bool {
                    // #4024: Bool BEFORE NSNumber — a bridged Bool IS an NSNumber
                    // (__NSCFBoolean), so testing NSNumber first rendered `true` as "1".
                    stringValue = String(bool)
                } else if let num = value as? NSNumber {
                    stringValue = num.stringValue
                } else {
                    stringValue = String(describing: value)
                }
                converted[key] = AnyValueAsString(stringValue)
            }
            metadata = converted.isEmpty ? nil : converted
        }

        return ActivityItem(
            id: response.id,
            type: response._type,
            level: response.level,
            timestamp: response.timestamp,
            message: response.message,
            workflowId: response.workflowId,
            batchId: response.batchId,
            threadId: response.threadId,
            nodeId: response.nodeId,
            metadataRaw: metadata,
            durationMs: response.durationMs,
            error: response.error
        )
    }

    /// Convert generated ActivityStatsResponse to app ActivityStats
    func convertToActivityStats(_ response: Components.Schemas.ActivityStatsResponse) -> ActivityStats {
        ActivityStats(
            totalActivities: response.totalActivities,
            activitiesByType: response.activitiesByType.additionalProperties,
            activitiesByLevel: response.activitiesByLevel.additionalProperties,
            errorCount: response.errorCount,
            warningCount: response.warningCount,
            avgWorkflowDurationMs: response.avgWorkflowDurationMs,
            successRate: response.successRate,
            periodStart: response.periodStart,
            periodEnd: response.periodEnd
        )
    }

    /// Convert generated checkpoint history to app type
    func convertToCheckpointHistory(
        _ response: Components.Schemas.CheckpointHistoryResponse,
        threadId: String
    ) -> CheckpointHistoryResponse {
        let checkpoints = response.checkpoints.map { checkpoint -> CheckpointSnapshot in
            // Convert state values
            var stateValues: [String: CheckpointValue] = [:]
            if let values = checkpoint.stateValues {
                for (key, value) in values.additionalProperties.value {
                    stateValues[key] = CheckpointValue(value as Any)
                }
            }

            // Convert writes
            var writes: [String: CheckpointValue] = [:]
            if let writeValues = checkpoint.writes {
                for (key, value) in writeValues.additionalProperties.value {
                    writes[key] = CheckpointValue(value as Any)
                }
            }

            return CheckpointSnapshot(
                checkpointId: checkpoint.checkpointId,
                parentCheckpointId: checkpoint.parentCheckpointId,
                step: checkpoint.step,
                timestamp: checkpoint.timestamp,
                nodeName: checkpoint.nodeName,
                stateValues: stateValues,
                writes: writes,
                nextNodes: checkpoint.nextNodes ?? []
            )
        }

        return CheckpointHistoryResponse(
            threadId: response.threadId,
            workflowId: response.workflowId,
            workflowName: response.workflowName,
            totalSteps: response.totalSteps,
            checkpoints: checkpoints
        )
    }
}
