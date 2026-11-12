import FicheroAPIClient
import Foundation

struct PairingQRCodePayload: Codable {
    let version: Int
    let apiURL: String
    let pairCode: String
    /// nil (the key left out) for an invitation that never expires; a decoder reads a missing key as never-expires.
    let expiresAt: Date?
    /// Absent when the advertised host's TLS is terminated by a public CA — a
    /// `tailscale serve` endpoint — because the host does not hold that key and
    /// must not claim it (#5041). Present for an engine serving its own cert.
    let spki: String?
    let libraryPath: String?
    /// The host's other addresses, in the order to try (`sharing.link-carries-every-address`). Absent in an old link, and an
    /// old client ignores it; `apiURL` stays the chosen first address.
    var altURLs: [String]?

    enum CodingKeys: String, CodingKey {
        case version = "v"
        case apiURL = "api_url"
        case pairCode = "pair_code"
        case expiresAt = "expires_at"
        case spki
        case libraryPath = "library_path"
        case altURLs = "alt_urls"
    }

    /// The most encoded characters a QR carries and a phone camera still reads at level M (`sharing.ios-qr-payload-size`).
    static let qrCharacterLimit = 400

    /// The payload as the QR carries it: no library path (the guest asks the host for it), and addresses dropped from the
    /// end until it fits. The chosen address is never the one dropped.
    func forQR() -> PairingQRCodePayload {
        var copy = PairingQRCodePayload(version: version, apiURL: apiURL, pairCode: pairCode, expiresAt: expiresAt,
                                        spki: spki, libraryPath: nil, altURLs: altURLs)
        while var alts = copy.altURLs, !alts.isEmpty, copy.encodedLength > Self.qrCharacterLimit {
            alts.removeLast()
            copy.altURLs = alts.isEmpty ? nil : alts
        }
        return copy
    }

    /// Length of the base64 of the payload's sorted JSON, the part a QR has to hold.
    var encodedLength: Int {
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = .sortedKeys
        return ((try? encoder.encode(self))?.base64EncodedString().count) ?? 0
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
    /// nil when the invitation never expires (`never_expires` beside it in the engine's answer).
    let expiresAt: Date?

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
    /// The paired device that minted this one; revoking that device revokes this one too (#5351).
    var pairedByDeviceId: String?
    /// The person signed in on this device, by name (#5738); nil from an older engine.
    var username: String?

    /// How the host's Inspector names it: "<person> on <device>", or just the device name when no person is known.
    var inspectorLabel: String {
        guard let username, !username.isEmpty else { return name }
        return "\(username) on \(name)"
    }

    enum CodingKeys: String, CodingKey {
        case id
        case name
        case pairedByDeviceId = "paired_by_device_id"
        case username
        case userId = "user_id"
        case createdAt = "created_at"
        case lastSeen = "last_seen"
        case expiresAt = "expires_at"
        case revoked
    }
}

@MainActor
final class PairingService {
    let client: FicheroClient

    /// Uses the transport the app resolved at launch, like every other service.
    ///
    /// Constructing a client from a base URL alone silently pinned pairing to
    /// HTTPS: every Release macOS build runs `.releaseEmbedded`, which dials a
    /// UDS socket (`EngineConfig+Launch.swift`), so pairing alone dialled
    /// `https://127.0.0.1:8765` where nothing listens. Sharing hung on
    /// "Preparing the security certificate" while every other call succeeded —
    /// and it hung in EVERY shipping build, because Debug resolves to `.https`
    /// and is the one configuration where the old code worked (#4224).
    init(apiRoot: URL) {
        self.client = FicheroClient(baseURL: apiRoot, transportMode: EngineConfig.transportMode)
    }

    init(apiRoot: URL, expectedSPKIPin: String?) throws {
        self.client = try FicheroClient(baseURL: apiRoot, expectedSPKIPin: expectedSPKIPin)
    }

    /// Share ONE folder of a project with a person who has an account (`sharing.settings.project-share-sheet`, #5967): the person
    /// reaches that folder and what is under it, nothing beside it. The engine grants the role on the folder at once and answers
    /// with a pairing code the person does not need (they already have an account).
    func shareFolder(username: String, role: String, library: String, folderId: String) async throws {
        let response = try await client.api.createPairingCodeApiPairCodePost(.init(body: .json(.init(
            username: username,
            role: role == "editor" ? .editor : .viewer,
            library: library,
            folderId: folderId
        ))))
        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            throw APIError.httpError(statusCode: 422, message: Self.validationWords(try? error.body.json))
        case .undocumented(let statusCode, let payload):
            // The engine refuses in words (the person already has the whole project, the folder is not in it, not the owner):
            // 4xx other than 422 is not in the contract, so the body is read as the other pairing calls read it.
            let detail = await EngineErrorDetail.message(from: payload)
            throw APIError.httpError(statusCode: statusCode, message: detail ?? "Unexpected response")
        }
    }

    /// `library`: the project the link is for, so the redeem gives this device that project
    /// (`sharing.link-grants-its-project`).
    func createPairingCode(library: String? = nil, also: [String] = []) async throws -> PairingCodeRecord {
        let body = library.map { Operations.CreatePairingCodeApiPairCodePost.Input.Body.json(.init(library: $0, libraries: also)) }
        let response = try await client.api.createPairingCodeApiPairCodePost(.init(body: body))
        switch response {
        case .ok(let okResponse):
            let record = try okResponse.body.json
            return PairingCodeRecord(code: record.code, expiresAt: record.expiresAt)
        case .unprocessableContent(let error):
            throw APIError.httpError(statusCode: 422, message: Self.validationWords(try? error.body.json))
        case .undocumented(let statusCode, let payload):
            let detail = await EngineErrorDetail.message(from: payload)
            throw APIError.httpError(statusCode: statusCode, message: detail ?? "Unexpected response")
        }
    }

    /// A 422's own messages ("a lifetime is for an invitation to a named person"), not the array's debug text.
    private static func validationWords(_ body: Components.Schemas.HTTPValidationError?) -> String {
        let words = (body?.detail ?? []).map(\.msg).joined(separator: "; ")
        return words.isEmpty ? "The engine did not accept that request." : words
    }

    /// Sharing state from the engine: the detected `.ts.net` address and, when the engine cannot
    /// make the tailnet forward itself (sandbox), the one command to paste (#5318, #5317).
    func sharingState() async throws -> SharingStateRecord {
        let response = try await client.api.sharingStateApiPairSharingGet(.init())
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            return SharingStateRecord(tailnetURL: body.tailnetUrl, tailnetServeCommand: body.tailnetServeCommand,
                                      auditId: body.auditId, publicBaseURL: body.publicBaseUrl, lanIP: body.lanIp,
                                      tailnetForward: body.tailnetForward?.rawValue,  // optional in the schema: a default is not `required`
                                      multiuserBlocker: body.multiuserBlocker,
                                      tailnetServeConflict: TailnetServeConflict(body.tailnetServeConflict?.additionalProperties),
                                      sharedLibraryCount: body.sharedLibraryCount)
        case .undocumented(let statusCode, _):
            throw APIError.httpError(statusCode: statusCode, message: "Unexpected response")
        }
    }

    /// This Mac's `.ts.net` address when Tailscale is running, else nil (#5318).
    func detectedTailnetURL() async throws -> String? {
        let response = try await client.api.detectedTailnetApiPairTailnetGet(.init())
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.tailnetUrl
        case .undocumented(let statusCode, _):
            throw APIError.httpError(statusCode: statusCode, message: "Unexpected response")
        }
    }

    /// Which client surfaces (app, CLI, MCP) have talked to the engine this
    /// session — the Sharing pane's "Connected Clients" list (2026-08-27).
    func connectedClients() async throws -> [ConnectedClientRecord] {
        let response = try await client.api.connectedClientsApiClientsGet(.init())
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            return body.clients.map {
                ConnectedClientRecord(
                    client: $0.client,
                    lastSeen: $0.lastSeen,
                    requests: Int($0.requests),
                    transport: $0.transport
                )
            }
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
                    revoked: device.revoked,
                    pairedByDeviceId: device.pairedByDeviceId,
                    username: device.username
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

    func pairDeviceUnauthenticated(
        code: String, deviceName: String, person: PairingPerson? = nil
    ) async throws -> PairingExchangeResponse {
        // `/api/pair` is accepted unauthenticated by the engine; the
        // AuthTokenMiddleware skips auth for this path so a local bootstrap
        // token is never forwarded to a remote host during pairing.
        let request = Components.Schemas.PairRequest(
            code: code, deviceName: deviceName, username: person?.username, password: person?.password
        )
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
        case .undocumented(let statusCode, let payload):
            let detail = await EngineErrorDetail.message(from: payload)
            if PairingPerson.isRequiredRefusal(status: statusCode, detail: detail) {
                throw RemoteClientPairingError.personRequired
            }
            throw APIError.httpError(statusCode: statusCode, message: detail ?? "Unexpected response")
        }
    }

    /// Build the QR / invite payload for an advertised engine.
    ///
    /// STATIC, and deliberately not a method on a configured service: this
    /// SENDS NOTHING. It describes where a phone should later connect, so its
    /// `apiRoot` is the externally reachable address — never the loopback
    /// share_url, and never the app's own transport.
    ///
    /// Those are different things IN KIND, and conflating them is a trap
    /// (#4224). The instance init now follows the app's resolved transport,
    /// which for a shipping macOS build is a UDS socket. Minting a payload
    /// through a configured service would therefore bake a socket PATH into a
    /// QR code — it would scan cleanly, look well-formed, and fail on a phone
    /// that cannot reach a filesystem socket on someone else's Mac. Nothing
    /// would error at mint time.
    ///
    /// Keeping this free of a client also makes the "one configured path to the
    /// engine" rule enforceable: with no legitimate `FicheroClient(baseURL:)`
    /// on the payload path, a guardrail for that construction has no exceptions
    /// to carve out.
    static func buildQRCodePayload(
        apiRoot: URL,
        from code: PairingCodeRecord,
        spki: String? = nil,
        libraryPath: String? = nil,
        alternates: [URL] = []
    ) -> PairingQRCodePayload {
        let root = { (url: URL) in url.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/")) }
        return PairingQRCodePayload(
            version: 1, apiURL: root(apiRoot), pairCode: code.code, expiresAt: code.expiresAt, spki: spki,
            libraryPath: libraryPath, altURLs: alternates.isEmpty ? nil : alternates.map(root))
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
