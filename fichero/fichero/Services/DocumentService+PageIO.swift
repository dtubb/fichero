//  DocumentService+PageIO.swift
//  Fichero
//
//  One page in and out as an interchange file (`source.format.everywhere`, #4943).
//
//  BOTH DIRECTIONS IN ONE FILE, and that is the point rather than a filing
//  convenience: an export that states its choices and its losses is only half of
//  "reads and writes PAGE XML, ALTO, TEI and eScriptorium", and the import is the
//  half that proves a scholar can get their work back out and in again. Keeping
//  them together is how the pair stays honest -- the same words for a pass, a
//  reading kind and a loss on each side.
//
//  Extracted from `DocumentService.swift` on 2026-09-27, when adding the import
//  took that file past its 1,000-line limit. The move also repaired a defect made
//  earlier the same night: `exportPage` had been inserted BETWEEN `exportWord`'s
//  doc comment and `exportWord` itself, so that method lost its documentation and
//  this one inherited a `- Parameters:` block describing `outputPath`, `targetId`
//  and `overwrite` -- none of which it has. A lint limit is a crude instrument, and
//  this time it pointed at something real.

import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

/// Page IO's own log category, rather than widening `DocumentService`'s `private` one.
///
/// A `private let logger` in that file is a deliberate boundary and an extension in another
/// file is on the far side of it. Dropping the `private` to reach it would widen access for
/// the whole app to fix one file's compile error; a category of its own costs one line and
/// makes `log stream --predicate 'category == "DocumentPageIO"'` show an import or an export
/// without the rest of the document traffic. Same subsystem, as every other service uses.
private let logger = Logger(subsystem: "app.fichero.fichero", category: "DocumentPageIO")

extension DocumentService {
    /// One page as an interchange format -- PAGE XML, ALTO or TEI.
    ///
    /// The response carries the file's text AND the choices the engine made
    /// (which pass, which reading order, which reading kind) AND what the
    /// format could not carry. All three matter: "export this page" is
    /// ambiguous the moment a page has two passes, and a loss nobody is told
    /// about is a loss that looks like a clean export.
    func exportPage(
        documentId: String,
        format: String,
        passId: String? = nil
    ) async throws -> Components.Schemas.PageExportResponse {
        logger.info("Exporting page \(documentId) as \(format)")

        // `passId` nil: the engine's choice (the working pass, or the working georeference), stated
        // back in `choices`. Set: the pass the person picked in Inspector › Making (#5162).
        let response = try await client.api.exportDocumentPageApiDocumentsDocIdExportFormatNameGet(
            .init(path: .init(docId: documentId, formatName: format), query: .init(passId: passId))
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        // Each refusal carries the ENGINE'S SENTENCE, and the `default` that used to stand here
        // threw `unexpectedResponse` for all of them. A 404 on this route says "document X has no
        // pass to export: nothing has been segmented or imported" -- which tells a scholar exactly
        // what to do -- and the app was replacing it with a word that names nothing. Declaring the
        // bodies (#5089's sibling) is what makes them readable; reading them is this half.
        case .notFound(let error):
            throw DocumentServiceError.serverError(try error.body.json.detail)
        case .conflict(let error):
            throw DocumentServiceError.serverError(try error.body.json.detail)
        case .unprocessableContent(let error):
            throw DocumentServiceError.serverError(try error.body.json.detail)
        case .undocumented(let statusCode, let payload):
            // Still here, and still last: a status the contract does not declare is exactly what
            // this branch is for, and silently succeeding on one would be worse than saying so.
            let detail = await Self.errorDetail(from: payload.body)
            throw DocumentServiceError.serverError(detail ?? "The engine answered \(statusCode).")
        }
    }

    /// The interchange formats this build reads and writes (`GET /api/formats`, #5162): what the
    /// export choices are built from, so a format the engine gains appears without an app change.
    func formats() async throws -> [PageExportChoice.Format] {
        let response = try await client.api.listFormatsApiFormatsGet()
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items.map {
                PageExportChoice.Format(name: $0.name, extensions: $0.extensions, writes: $0.writes)
            }
        case .undocumented(let statusCode, _):
            throw DocumentServiceError.serverError("The engine answered \(statusCode) for its formats.")
        }
    }

    /// One interchange file into a page as a NEW PASS (`source.format.import-is-pass`).
    ///
    /// Returns an `Outcome`, not a bare result, because "this exact file is already
    /// here" (409) is an ANSWER and not a failure: the engine names the pass that
    /// holds the same bytes, and the app says so. Everything else the engine refuses
    /// (a file nothing recognises, shapes outside the declared page) is thrown with
    /// the engine's own sentence.
    ///
    /// `longRunningAPI`: a dense page is thousands of segments and the import scales
    /// with the file, not with server health.
    func importPage(
        documentId: String,
        data: Data,
        filename: String,
        format: String? = nil
    ) async throws -> PageImportRunner.Outcome {
        logger.info("Importing \(filename) into page \(documentId)")

        let part = OpenAPIRuntime.MultipartPart(
            payload: Components.Schemas.BodyImportDocumentPageApiDocumentsDocIdImportPost.FilePayload(
                body: OpenAPIRuntime.HTTPBody(data)
            ),
            filename: filename
        )
        let response = try await client.longRunningAPI.importDocumentPageApiDocumentsDocIdImportPost(
            .init(
                path: .init(docId: documentId),
                query: .init(format: format, name: filename),
                body: .multipartForm([.file(part)])
            )
        )

        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.json
            return .imported(PageImportRunner.Result(
                passId: body.passId,
                format: body.format,
                segments: Int(body.segments),
                readings: Int(body.readings),
                orderEntries: Int(body.orderEntries),
                geometryProblems: Int(body.geometryProblems ?? 0)
            ))
        // Every refusal below hands the person THE ENGINE'S OWN SENTENCE. "Nothing
        // recognises 'x.xml'. This build reads: ..." is what tells a scholar what to do
        // next; a message the app invented in its place would be the app guessing at the
        // engine's meaning, and the next refusal added would not be in the guess.
        case .conflict(let answer):
            // NOT a failure, and it stopped being `.undocumented` when the route declared
            // its error bodies (#5089). It used to work only because nothing declared the
            // 409 -- the same accident facing the other way -- and it now arrives typed.
            return .alreadyImported(detail: try answer.body.json.detail)
        case .notFound(let error):
            throw DocumentServiceError.serverError(try error.body.json.detail)
        case .unprocessableContent(let error):
            // `ErrorDetail.detail` is a required String, so there is no optional to
            // unwrap and no "Validation error" placeholder to fall back to. That
            // placeholder was the thing #5089 existed to remove.
            throw DocumentServiceError.serverError(try error.body.json.detail)
        case .undocumented(let statusCode, let payload):
            let detail = await Self.errorDetail(from: payload.body)
            throw DocumentServiceError.serverError(detail ?? "The engine answered \(statusCode).")
        }
    }

    /// The `{"detail": "..."}` sentence an engine refusal carries, if it has one.
    ///
    /// Only for a status the contract does NOT declare. Everything the route declares is
    /// read from its typed body instead -- reaching into a raw payload for a documented
    /// response would be keeping a second, hand-rolled decoder beside the generated one.
    private static func errorDetail(from body: OpenAPIRuntime.HTTPBody?) async -> String? {
        guard let body, let data = try? await Data(collecting: body, upTo: 1_048_576) else { return nil }
        struct Detail: Decodable { let detail: String }
        return (try? JSONDecoder().decode(Detail.self, from: data))?.detail
    }
}
