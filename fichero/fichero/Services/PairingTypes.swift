import FicheroAPIClient
import Foundation

struct PairingQRCodePayload: Codable {
    let version: Int
    let apiURL: String
    let pairCode: String
    let expiresAt: Date
    let spki: String
    let libraryPath: String?

    enum CodingKeys: String, CodingKey {
        case version = "v"
        case apiURL = "api_url"
        case pairCode = "pair_code"
        case expiresAt = "expires_at"
        case spki
        case libraryPath = "library_path"
    }
}

enum PairingQRCodePayloadDecoder {
    static func decode(message: String) throws -> PairingQRCodePayload {
        guard let payloadData = message.data(using: .utf8) else {
            throw APIError.badRequest("The QR code payload was not valid UTF-8.")
        }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let raw = try container.decode(String.self)
            guard let date = parseEngineDate(raw) else {
                throw DecodingError.dataCorruptedError(
                    in: container,
                    debugDescription: "Cannot decode QR payload date: \(raw)"
                )
            }
            return date
        }

        return try decoder.decode(PairingQRCodePayload.self, from: payloadData)
    }
}

struct PairingCodeRecord: Codable {
    let code: String
    let expiresAt: Date

    enum CodingKeys: String, CodingKey {
        case code
        case expiresAt = "expires_at"
    }
}

struct PairingExchangeRequest: Codable {
    let code: String
    let deviceName: String

    enum CodingKeys: String, CodingKey {
        case code
        case deviceName = "device_name"
    }
}

struct PairingExchangeResponse: Codable {
    let deviceId: String
    let deviceToken: String
    /// When this device token expires — used to schedule proactive renewal (#3096).
    let expiresAt: Date

    enum CodingKeys: String, CodingKey {
        case deviceId = "device_id"
        case deviceToken = "device_token"
        case expiresAt = "expires_at"
    }
}

struct PairingExchangeResult: Equatable {
    let apiRoot: URL
    let deviceToken: String
    /// Device-token expiry carried from the pair response (#3096) so it can be
    /// persisted for renewal scheduling.
    let expiresAt: Date
}

struct PairedDeviceRecord: Codable, Identifiable {
    let id: String
    let name: String
    let userId: String
    let createdAt: Date
    let lastSeen: Date
    let expiresAt: Date
    let revoked: Bool

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case userId = "user_id"
        case createdAt = "created_at"
        case lastSeen = "last_seen"
        case expiresAt = "expires_at"
        case revoked
    }
}

@MainActor
final class PairingService {
    private let client: FicheroClient

    init(apiRoot: URL) {
        self.client = FicheroClient(baseURL: apiRoot)
    }

    init(apiRoot: URL, expectedSPKIPin: String) throws {
        self.client = try FicheroClient(baseURL: apiRoot, expectedSPKIPin: expectedSPKIPin)
    }

    func createPairingCode() async throws -> PairingCodeRecord {
        let response = try await client.api.createPairingCodeApiPairCodePost(.init())
        switch response {
        case .ok(let okResponse):
            let record = try okResponse.body.json
            return PairingCodeRecord(code: record.code, expiresAt: record.expiresAt)
        case .undocumented(let statusCode, _):
            throw APIError.httpError(statusCode: statusCode, message: "Unexpected response")
        }
    }

    func listDevices() async throws -> [PairedDeviceRecord] {
        let response = try await client.api.listDevicesApiPairDevicesGet(.init())
        switch response {
        case .ok(let okResponse):
            let list = try okResponse.body.json
            return list.items.map { device in
                PairedDeviceRecord(
                    id: device.id,
                    name: device.name,
                    userId: device.userId,
                    createdAt: device.createdAt,
                    lastSeen: device.lastSeen,
                    expiresAt: device.expiresAt,
                    revoked: device.revoked
                )
            }
        case .undocumented(let statusCode, _):
            throw APIError.httpError(statusCode: statusCode, message: "Unexpected response")
        }
    }

    func revokeDevice(id: String) async throws {
        let response = try await client.api.revokeDeviceApiPairDevicesDeviceIdRevokePost(
            path: .init(deviceId: id)
        )
        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw APIError.httpError(statusCode: 422, message: detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw APIError.httpError(statusCode: statusCode, message: "Unexpected response")
        }
    }

    func pairDeviceUnauthenticated(code: String, deviceName: String) async throws -> PairingExchangeResponse {
        // `/api/pair` is accepted unauthenticated by the engine; the
        // AuthTokenMiddleware skips auth for this path so a local bootstrap
        // token is never forwarded to a remote host during pairing.
        let request = Components.Schemas.PairRequest(code: code, deviceName: deviceName)
        let response = try await client.api.pairDeviceApiPairPost(.init(body: .json(request)))
        switch response {
        case .ok(let okResponse):
            let record = try okResponse.body.json
            return PairingExchangeResponse(
                deviceId: record.deviceId,
                deviceToken: record.deviceToken,
                expiresAt: record.expiresAt
            )
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw APIError.httpError(statusCode: 422, message: detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw APIError.httpError(statusCode: statusCode, message: "Unexpected response")
        }
    }

    func buildQRCodePayload(
        from code: PairingCodeRecord,
        spki: String = "",
        libraryPath: String? = nil
    ) -> PairingQRCodePayload {
        PairingQRCodePayload(
            version: 1,
            apiURL: client.baseURL.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")),
            pairCode: code.code,
            expiresAt: code.expiresAt,
            spki: spki,
            libraryPath: libraryPath
        )
    }

    /// The library paths this credential may access on the paired engine,
    /// from `GET /api/authz/libraries` (app-wide, no library header needed).
    /// Used by pairing to confirm a QR-advertised library before persisting it
    /// (#3372). Mirrors `KnownLibraryRegistryStore.refreshAccessible`.
    func accessibleLibraryPaths() async throws -> [String] {
        let response = try await client.api.listAccessibleLibrariesApiAuthzLibrariesGet()
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items.map(\.libraryPath)
        case .undocumented(let statusCode, _):
            throw APIError.httpError(statusCode: statusCode, message: "Unexpected response")
        }
    }

    static func persistAuthToken(_ token: String, for apiRoot: URL) throws {
        try AuthTokenMiddleware.persistRemoteToken(token, hostString: apiRoot.absoluteString)
    }
}
