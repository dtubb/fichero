import Foundation

/// Centralized API endpoint definitions.
///
/// This file serves as the single source of truth for API paths in Swift.
/// All services should use these constants instead of hardcoded strings.
///
/// To validate these match the Python API, run:
///   python scripts/export_openapi_schema.py
/// Then run the Swift EndpointValidationTests.
///
enum APIEndpoints {

    // MARK: - Health

    enum Health {
        static let check = "/health"
    }

    // MARK: - Documents

    enum Documents {
        static let base = "/documents"
        static let list = "/documents"
        static let collections = "/documents/collections"
        static let roots = "/documents/roots"

        static func get(_ id: String) -> String { "/documents/\(id)" }
        static func update(_ id: String) -> String { "/documents/\(id)" }
        static func delete(_ id: String) -> String { "/documents/\(id)" }
        static func children(_ id: String) -> String { "/documents/\(id)/children" }
        static func ancestors(_ id: String) -> String { "/documents/\(id)/ancestors" }
        static func move(_ id: String) -> String { "/documents/\(id)/move" }

        static let create = "/documents"
        static let reorder = "/documents/reorder"
        static let importFiles = "/documents/import"
    }

    // MARK: - Workflows

    enum Workflows {
        static let base = "/workflows"
        static let list = "/workflows"
        static let create = "/workflows"
        static let tools = "/workflows/tools"
        static let toolsGrouped = "/workflows/tools/grouped"
        static let reorder = "/workflows/reorder"
        static let importWorkflow = "/workflows/import"

        static func get(_ id: String) -> String { "/workflows/\(id)" }
        static func update(_ id: String) -> String { "/workflows/\(id)" }
        static func delete(_ id: String) -> String { "/workflows/\(id)" }
        static func duplicate(_ id: String) -> String { "/workflows/\(id)/duplicate" }
        static func export(_ id: String) -> String { "/workflows/\(id)/export" }
        static func tool(_ name: String) -> String { "/workflows/tools/\(name)" }
        static func createNode(_ toolName: String) -> String { "/workflows/tools/\(toolName)/create-node" }
    }

    // MARK: - Search

    enum Search {
        static let search = "/search"
        static let stats = "/search/stats"
        static let reindex = "/search/reindex"
        static let saved = "/search/saved"
        static let savedReorder = "/search/saved/reorder"

        static func embed(_ docId: String) -> String { "/search/embed/\(docId)" }
        static func savedGet(_ id: String) -> String { "/search/saved/\(id)" }
        static func savedUpdate(_ id: String) -> String { "/search/saved/\(id)" }
        static func savedDelete(_ id: String) -> String { "/search/saved/\(id)" }
        static func savedDuplicate(_ id: String) -> String { "/search/saved/\(id)/duplicate" }
    }

    // MARK: - Chat

    enum Chat {
        static let send = "/chat"
        static let conversations = "/chat/conversations"
        static let conversationsReorder = "/chat/conversations/reorder"
        static let providers = "/chat/providers"
        static let extractText = "/chat/extract-text"

        static func conversation(_ id: String) -> String { "/chat/conversations/\(id)" }
        static func conversationUpdate(_ id: String) -> String { "/chat/conversations/\(id)" }
        static func conversationDelete(_ id: String) -> String { "/chat/conversations/\(id)" }
        static func conversationDuplicate(_ id: String) -> String { "/chat/conversations/\(id)/duplicate" }
    }

    // MARK: - Providers

    enum Providers {
        static let catalog = "/providers/catalog"
        static let list = "/providers"
        static let create = "/providers"
        static let refs = "/providers/refs"

        static func catalogProvider(_ type: String) -> String { "/providers/catalog/\(type)" }
        static func models(_ type: String) -> String { "/providers/models/\(type)" }
        static func get(_ id: String) -> String { "/providers/\(id)" }
        static func update(_ id: String) -> String { "/providers/\(id)" }
        static func delete(_ id: String) -> String { "/providers/\(id)" }
        static func providerModels(_ id: String) -> String { "/providers/\(id)/models" }
        static func apiKey(_ type: String) -> String { "/providers/\(type)/api-key" }
        static func apiKeyStatus(_ type: String) -> String { "/providers/\(type)/api-key/status" }
        static func test(_ type: String) -> String { "/providers/\(type)/test" }
        static func refUpdate(_ id: String) -> String { "/providers/refs/\(id)" }
        static func refDelete(_ id: String) -> String { "/providers/refs/\(id)" }
    }

    // MARK: - Storage

    enum Storage {
        static let stats = "/storage/stats"

        static func thumbnail(_ docId: String) -> String { "/storage/thumbnail/\(docId)" }
        static func display(_ docId: String) -> String { "/storage/display/\(docId)" }
        static func source(_ docId: String) -> String { "/storage/source/\(docId)" }
        static func debug(_ docId: String) -> String { "/storage/debug/\(docId)" }
    }

    // MARK: - Ingest

    enum Ingest {
        static let file = "/ingest/file"
        static let folder = "/ingest/folder"

        static func status(_ taskId: String) -> String { "/ingest/status/\(taskId)" }
    }

    // MARK: - Batches

    enum Batches {
        static let list = "/batches"
        static let create = "/batches"

        static func get(_ id: String) -> String { "/batches/\(id)" }
        static func progress(_ id: String) -> String { "/batches/\(id)/progress" }
        static func execute(_ id: String) -> String { "/batches/\(id)/execute" }
        static func pause(_ id: String) -> String { "/batches/\(id)/pause" }
        static func resume(_ id: String) -> String { "/batches/\(id)/resume" }
        static func cancel(_ id: String) -> String { "/batches/\(id)/cancel" }
        static func retry(_ id: String) -> String { "/batches/\(id)/retry" }
        static func delete(_ id: String) -> String { "/batches/\(id)" }
    }

    // MARK: - Activity

    enum Activity {
        static let list = "/activity"
        static let recent = "/activity/recent"
        static let stats = "/activity/stats"
        static let stream = "/activity/stream"
        static let cleanup = "/activity/cleanup"

        static func forWorkflow(_ id: String) -> String { "/activity/workflow/\(id)" }
        static func forBatch(_ id: String) -> String { "/activity/batch/\(id)" }
    }

    // MARK: - Schedules

    enum Schedules {
        static let list = "/schedules"
        static let create = "/schedules"

        static func get(_ id: String) -> String { "/schedules/\(id)" }
        static func delete(_ id: String) -> String { "/schedules/\(id)" }
        static func pause(_ id: String) -> String { "/schedules/\(id)/pause" }
        static func resume(_ id: String) -> String { "/schedules/\(id)/resume" }
        static func trigger(_ id: String) -> String { "/schedules/\(id)/trigger" }
        static func runs(_ id: String) -> String { "/schedules/\(id)/runs" }
    }

    // MARK: - Triggers

    enum Triggers {
        static let list = "/triggers"
        static let create = "/triggers"

        static func get(_ id: String) -> String { "/triggers/\(id)" }
        static func delete(_ id: String) -> String { "/triggers/\(id)" }
        static func pause(_ id: String) -> String { "/triggers/\(id)/pause" }
        static func resume(_ id: String) -> String { "/triggers/\(id)/resume" }
        static func executions(_ id: String) -> String { "/triggers/\(id)/executions" }
    }

    // MARK: - Folders

    enum Folders {
        static func list(_ entityType: String) -> String { "/folders/\(entityType)/folders" }
        static func create(_ entityType: String) -> String { "/folders/\(entityType)/folders" }
        static func update(_ entityType: String) -> String { "/folders/\(entityType)/folders" }
        static func delete(_ entityType: String) -> String { "/folders/\(entityType)/folders" }
        static func move(_ entityType: String) -> String { "/folders/\(entityType)/move" }
    }
}

// MARK: - Endpoint Method Definitions (for validation)

/// Defines expected HTTP methods for each endpoint pattern.
/// Used by tests to validate Swift services use correct methods.
struct EndpointDefinition {
    let method: String  // GET, POST, PUT, PATCH, DELETE
    let pathPattern: String  // e.g., "/workflows/{id}"

    static let definitions: [EndpointDefinition] = [
        // Documents
        EndpointDefinition(method: "GET", pathPattern: "/documents"),
        EndpointDefinition(method: "POST", pathPattern: "/documents"),
        EndpointDefinition(method: "GET", pathPattern: "/documents/{id}"),
        EndpointDefinition(method: "PUT", pathPattern: "/documents/{id}"),
        EndpointDefinition(method: "DELETE", pathPattern: "/documents/{id}"),

        // Workflows
        EndpointDefinition(method: "GET", pathPattern: "/workflows"),
        EndpointDefinition(method: "POST", pathPattern: "/workflows"),
        EndpointDefinition(method: "GET", pathPattern: "/workflows/{id}"),
        EndpointDefinition(method: "PUT", pathPattern: "/workflows/{id}"),
        EndpointDefinition(method: "DELETE", pathPattern: "/workflows/{id}"),
        EndpointDefinition(method: "POST", pathPattern: "/workflows/{id}/duplicate"),

        // Search
        EndpointDefinition(method: "POST", pathPattern: "/search"),
        EndpointDefinition(method: "GET", pathPattern: "/search/saved"),
        EndpointDefinition(method: "POST", pathPattern: "/search/saved"),
        EndpointDefinition(method: "PUT", pathPattern: "/search/saved/{id}"),
        EndpointDefinition(method: "DELETE", pathPattern: "/search/saved/{id}"),

        // Chat
        EndpointDefinition(method: "POST", pathPattern: "/chat"),
        EndpointDefinition(method: "GET", pathPattern: "/chat/conversations"),
        EndpointDefinition(method: "GET", pathPattern: "/chat/conversations/{id}"),
        EndpointDefinition(method: "PUT", pathPattern: "/chat/conversations/{id}"),
        EndpointDefinition(method: "DELETE", pathPattern: "/chat/conversations/{id}"),
    ]
}
