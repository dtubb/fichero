import Foundation
import OSLog
import FicheroAPIClient
import OpenAPIRuntime
import OpenAPIURLSession

private let logger = Logger(subsystem: "com.fichero.fichero", category: "HermeneuticsServiceGenerated")

/// Service for interacting with the Hermeneutics API (interpretations, frameworks, patterns, circle navigation)
@MainActor
class HermeneuticsServiceGenerated {
    private let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    convenience init(apiClient: APIClient) {
        let libraryPath = apiClient.currentLibraryPath ?? ""
        let ficheroClient = FicheroClient(libraryPath: libraryPath)
        self.init(ficheroClient: ficheroClient)
    }

    // MARK: - Frameworks

    /// List all hermeneutic frameworks
    func listFrameworks() async throws -> [Components.Schemas.InterpretiveFramework] {
        let response = try await client.api.listFrameworksApiHermeneuticsFrameworksGet(
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw HermeneuticsServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw HermeneuticsServiceError.unexpectedResponse(code)
        }
    }

    /// Create a new hermeneutic framework
    func createFramework(
        name: String,
        frameworkType: Components.Schemas.FrameworkType = .theoretical,
        description: String? = nil
    ) async throws -> Components.Schemas.InterpretiveFramework {
        var body = Components.Schemas.FrameworkCreateRequest(
            name: name,
            frameworkType: frameworkType,
            description: description ?? ""
        )

        let response = try await client.api.createFrameworkApiHermeneuticsFrameworksPost(
            body: .json(body),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw HermeneuticsServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw HermeneuticsServiceError.unexpectedResponse(code)
        }
    }

    /// Get framework by ID
    func getFramework(frameworkId: String) async throws -> Components.Schemas.InterpretiveFramework {
        let response = try await client.api.getFrameworkApiHermeneuticsFrameworksFrameworkIdGet(
            path: .init(frameworkId: frameworkId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw HermeneuticsServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw HermeneuticsServiceError.unexpectedResponse(code)
        }
    }

    /// Delete a framework
    func deleteFramework(frameworkId: String) async throws {
        let response = try await client.api.deleteFrameworkApiHermeneuticsFrameworksFrameworkIdDelete(
            path: .init(frameworkId: frameworkId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw HermeneuticsServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw HermeneuticsServiceError.unexpectedResponse(code)
        }
    }

    // MARK: - Interpretations

    /// List interpretations, optionally filtered by framework
    func listInterpretations(frameworkId: String? = nil, claimId: String? = nil, limit: Int = 100) async throws -> [Components.Schemas.Interpretation] {
        let response = try await client.api.listInterpretationsApiHermeneuticsInterpretationsGet(
            query: .init(frameworkId: frameworkId, claimId: claimId, limit: limit),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw HermeneuticsServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw HermeneuticsServiceError.unexpectedResponse(code)
        }
    }

    /// Create an interpretation
    func createInterpretation(
        frameworkId: String,
        interpretationText: String,
        claimId: String? = nil,
        documentId: String? = nil,
        passageText: String? = nil,
        act: Components.Schemas.InterpretiveActType? = nil,
        confidence: Double = 0.5
    ) async throws -> Components.Schemas.Interpretation {
        var body = Components.Schemas.InterpretationCreateRequest(
            frameworkId: frameworkId,
            interpretationText: interpretationText,
            confidence: confidence
        )
        body.claimId = claimId
        body.documentId = documentId
        body.passageText = passageText
        body.act = act

        let response = try await client.api.createInterpretationApiHermeneuticsInterpretationsPost(
            body: .json(body),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw HermeneuticsServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw HermeneuticsServiceError.unexpectedResponse(code)
        }
    }

    /// Get interpretation by ID
    func getInterpretation(interpretationId: String) async throws -> Components.Schemas.Interpretation {
        let response = try await client.api.getInterpretationApiHermeneuticsInterpretationsInterpretationIdGet(
            path: .init(interpretationId: interpretationId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw HermeneuticsServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw HermeneuticsServiceError.unexpectedResponse(code)
        }
    }

    // MARK: - Patterns

    /// List all hermeneutic patterns
    func listPatterns() async throws -> [Components.Schemas.PatternInstance] {
        let response = try await client.api.listPatternsApiHermeneuticsPatternsGet(
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw HermeneuticsServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw HermeneuticsServiceError.unexpectedResponse(code)
        }
    }

    /// Add a claim to a pattern
    func addClaimToPattern(patternId: String, claimId: String) async throws {
        let response = try await client.api.addClaimToPatternApiHermeneuticsPatternsPatternIdClaimsClaimIdPost(
            path: .init(patternId: patternId, claimId: claimId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw HermeneuticsServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw HermeneuticsServiceError.unexpectedResponse(code)
        }
    }

    // MARK: - Hermeneutic Circle

    /// List circle states (navigation stack)
    func listCircleStates() async throws -> [Components.Schemas.HermeneuticCircleState] {
        let response = try await client.api.listCircleStatesApiHermeneuticsCircleStateGet(
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw HermeneuticsServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw HermeneuticsServiceError.unexpectedResponse(code)
        }
    }

    /// Create a circle state (enter hermeneutic circle)
    func createCircleState(
        frameworkId: String,
        startingClaimId: String? = nil,
        startingInterpretationId: String? = nil
    ) async throws -> Components.Schemas.HermeneuticCircleState {
        var body = Components.Schemas.CircleStateCreateRequest(frameworkId: frameworkId)
        body.startingClaimId = startingClaimId
        body.startingInterpretationId = startingInterpretationId

        let response = try await client.api.createCircleStateApiHermeneuticsCircleStatePost(
            body: .json(body),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw HermeneuticsServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw HermeneuticsServiceError.unexpectedResponse(code)
        }
    }

    /// Get current circle state
    func getCircleState(stateId: String) async throws -> Components.Schemas.HermeneuticCircleState {
        let response = try await client.api.getCircleStateApiHermeneuticsCircleStateStateIdGet(
            path: .init(stateId: stateId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw HermeneuticsServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw HermeneuticsServiceError.unexpectedResponse(code)
        }
    }

    /// Navigate (step forward in the circle)
    func navigateCircle(stateId: String, targetClaimId: String? = nil, targetInterpretationId: String? = nil) async throws -> Components.Schemas.HermeneuticCircleState {
        var body = Components.Schemas.CircleStateNavigateRequest()
        body.targetClaimId = targetClaimId
        body.targetInterpretationId = targetInterpretationId

        let response = try await client.api.navigateCircleApiHermeneuticsCircleStateStateIdNavigatePost(
            path: .init(stateId: stateId),
            body: .json(body),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw HermeneuticsServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw HermeneuticsServiceError.unexpectedResponse(code)
        }
    }

    /// Backtrack in the circle
    func backtrackCircle(stateId: String) async throws -> Components.Schemas.HermeneuticCircleState {
        let response = try await client.api.backtrackCircleApiHermeneuticsCircleStateStateIdBacktrackPost(
            path: .init(stateId: stateId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw HermeneuticsServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw HermeneuticsServiceError.unexpectedResponse(code)
        }
    }
}

// MARK: - Error Types

enum HermeneuticsServiceError: LocalizedError {
    case validationError(String)
    case unexpectedResponse(Int)

    var errorDescription: String? {
        switch self {
        case .validationError(let message):
            return "Validation error: \(message)"
        case .unexpectedResponse(let statusCode):
            return "Unexpected response: HTTP \(statusCode)"
        }
    }
}
