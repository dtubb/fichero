// fm-bridge — minimal CLI wrapper around Foundation Models.
//
// Reads a JSON request from stdin, runs an Apple Intelligence LLM call
// via FoundationModels.LanguageModelSession, writes a JSON response to
// stdout. Exits non-zero on errors with a JSON error payload on stderr.
//
// This bridge exists because FoundationModels' public API is Swift-native
// and not @objc-exposed, so pyobjc can load the classes but can't call
// `respond(to:)`. Python's `chat()` subprocesses this binary instead.
//
// Build (dev): swiftc -O -o fm-bridge main.swift
// Build (universal release): see scripts/build_fm_bridge.sh
//
// Request shape (stdin):
//   {"prompt": "...", "instructions": "..." (optional)}
//
// Response shape (stdout, on success):
//   {"response": "...", "model": "apple-intelligence"}
//
// Error shape (stderr, on failure):
//   {"error": "...", "kind": "unavailable|generation|json"}

import Foundation
import FoundationModels

struct Request: Codable {
    let prompt: String
    let instructions: String?
}

struct SuccessResponse: Codable {
    let response: String
    let model: String
}

struct ErrorResponse: Codable {
    let error: String
    let kind: String
}

func emitError(_ message: String, kind: String) -> Never {
    let err = ErrorResponse(error: message, kind: kind)
    if let data = try? JSONEncoder().encode(err) {
        FileHandle.standardError.write(data)
    }
    exit(1)
}

/// Emit a probe result `{"available": Bool, "reason": String?}` to stdout
/// and exit. Used by `--probe` mode for the onboarding wizard's "Is Apple
/// Intelligence available on this Mac?" check, so we don't have to spin up
/// a real generation to find out.
struct ProbeResponse: Codable {
    let available: Bool
    let reason: String?
}

func emitProbe(available: Bool, reason: String?) -> Never {
    let payload = ProbeResponse(available: available, reason: reason)
    if let data = try? JSONEncoder().encode(payload) {
        FileHandle.standardOutput.write(data)
    }
    exit(available ? 0 : 1)
}

@main
struct FmBridge {
    static func main() async {
        // Probe mode — availability check only, no generation. Runs in tens
        // of milliseconds; safe to call from the wizard's onAppear.
        if CommandLine.arguments.contains("--probe") {
            let model = SystemLanguageModel.default
            switch model.availability {
            case .available:
                emitProbe(available: true, reason: nil)
            default:
                emitProbe(
                    available: false,
                    reason: "Apple Intelligence is not available on this device. " +
                            "Requires macOS 26+ on Apple Silicon with Apple Intelligence enabled."
                )
            }
        }

        // Availability check first — fail fast on machines without
        // Apple Intelligence (older OS, unsupported chip, not opted-in).
        let model = SystemLanguageModel.default
        guard case .available = model.availability else {
            emitError(
                "Apple Intelligence is not available on this device. " +
                "Requires macOS 26+ on Apple Silicon with Apple Intelligence enabled.",
                kind: "unavailable"
            )
        }

        // Read JSON request from stdin.
        let inputData = FileHandle.standardInput.readDataToEndOfFile()
        guard !inputData.isEmpty else {
            emitError("Empty stdin", kind: "json")
        }

        let request: Request
        do {
            request = try JSONDecoder().decode(Request.self, from: inputData)
        } catch {
            emitError(
                "Couldn't parse stdin as Request JSON: \(error)",
                kind: "json"
            )
        }

        // Run a single-shot generation.
        let session: LanguageModelSession
        if let instructions = request.instructions, !instructions.isEmpty {
            session = LanguageModelSession(instructions: instructions)
        } else {
            session = LanguageModelSession()
        }

        do {
            let result = try await session.respond(to: request.prompt)
            let payload = SuccessResponse(
                response: result.content,
                model: "apple-intelligence"
            )
            let data = try JSONEncoder().encode(payload)
            FileHandle.standardOutput.write(data)
        } catch {
            emitError("Generation failed: \(error)", kind: "generation")
        }
    }
}
