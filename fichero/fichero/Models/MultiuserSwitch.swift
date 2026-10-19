import Foundation

/// The persisted Multi-user switch, set through the engine's audited action so ⌘Z takes it back
/// (`undo.one-path`, #5751): changing it changes who sees every library. The step goes on the
/// window's `UndoManager` through `WindowSteps`, like every person-started change.
@MainActor
enum MultiuserSwitch {
    @discardableResult
    static func set(
        _ enabled: Bool, pairing: PairingService, service: (any UndoSetEngine)?, steps: WindowSteps?
    ) async throws -> SharingStateRecord {
        try await UndoableChange.run(
            named: enabled ? "Turn On Multi-user" : "Turn Off Multi-user", service: service, steps: steps,
            { try await put(enabled, pairing: pairing) },
            auditIds: { $0.auditId.map { [$0] } ?? [] }
        )
    }

    private static func put(_ enabled: Bool, pairing: PairingService) async throws -> SharingStateRecord {
        let api = pairing.client.api
        let response = try await api.setMultiuserApiPairMultiuserPut(body: .json(.init(enabled: enabled)))
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            return SharingStateRecord(tailnetURL: body.tailnetUrl, tailnetServeCommand: body.tailnetServeCommand,
                                      auditId: body.auditId)
        case .unprocessableContent:
            throw APIError.httpError(statusCode: 422, message: "Unexpected response")
        case .undocumented(let statusCode, _):
            throw APIError.httpError(statusCode: statusCode, message: "Unexpected response")
        }
    }
}
