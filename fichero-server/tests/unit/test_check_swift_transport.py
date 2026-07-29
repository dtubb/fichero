"""Unit tests for scripts/check_swift_transport.py (#2606, #2608)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "check_swift_transport.py"
_SPEC = importlib.util.spec_from_file_location("check_swift_transport", _SCRIPT)
assert _SPEC and _SPEC.loader
_mod = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _mod
_SPEC.loader.exec_module(_mod)  # type: ignore[attr-defined]

scan = _mod.scan


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_flags_raw_urlsession_shared(tmp_path: Path) -> None:
    _write(tmp_path, "Views/V.swift", "let (d, r) = try await URLSession.shared.data(for: req)\n")
    assert scan(tmp_path)


def test_flags_raw_urlsession_configuration(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Services/S.swift",
        "let session = URLSession(configuration: .ephemeral)\n",
    )
    assert scan(tmp_path)


def test_allows_pinned_configured_session(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Services/S.swift",
        "let session = RemoteCertificatePinning.configuredSession()\n",
    )
    assert not scan(tmp_path)


def test_allows_pinned_configured_session_with_config(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Services/S.swift",
        "let session = RemoteCertificatePinning.configuredSession(configuration: config)\n",
    )
    assert not scan(tmp_path)


def test_flags_local_pinned_session_with_bytes(tmp_path: Path) -> None:
    """A per-call local pinned session used with .bytes( must FAIL (#2605 / #2608)."""
    _write(
        tmp_path,
        "Services/S.swift",
        """@MainActor
final class S {
    func stream() async throws {
        var request = URLRequest(url: URL(string: "https://127.0.0.1:8765/api/stream")!)
        let session = RemoteCertificatePinning.configuredSession()
        let (bytes, response) = try await session.bytes(for: request)
        _ = response
        for try await _ in bytes.lines {}
    }
}
""",
    )
    assert scan(tmp_path)


def test_allows_stored_pinned_session_with_bytes(tmp_path: Path) -> None:
    """A class-level stored pinned session used with .bytes( must PASS (#2608)."""
    _write(
        tmp_path,
        "Services/S.swift",
        """@MainActor
final class S {
    private let urlSession: URLSession = RemoteCertificatePinning.configuredSession()

    func stream() async throws {
        var request = URLRequest(url: URL(string: "https://127.0.0.1:8765/api/stream")!)
        let (bytes, response) = try await urlSession.bytes(for: request)
        _ = response
        for try await _ in bytes.lines {}
    }
}
""",
    )
    assert not scan(tmp_path)


def test_flags_plain_http_engine_url(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Views/V.swift",
        'let base = "http://127.0.0.1:8765/api/v1"\n',
    )
    assert scan(tmp_path)


def test_allows_external_http_url(tmp_path: Path) -> None:
    # Local provider endpoints (Ollama, LM Studio) are not the Fichero engine.
    _write(
        tmp_path,
        "Views/V.swift",
        'return "http://localhost:11434/v1/chat"\n',
    )
    assert not scan(tmp_path)


def test_flags_wkwebview_challenge_handler_with_plain_signature(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Views/V.swift",
        """final class C: NSObject, WKNavigationDelegate {
    func webView(
        _ webView: WKWebView,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        completionHandler(.performDefaultHandling, nil)
    }
}
""",
    )
    assert scan(tmp_path)


def test_allows_wkwebview_challenge_handler_with_pinned_signature(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Views/V.swift",
        """final class C: NSObject, WKNavigationDelegate {
    @MainActor
    func webView(
        _ webView: WKWebView,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: @escaping @MainActor @Sendable (URLSession.AuthChallengeDisposition, URLCredential?) -> Void
    ) {
        let (d, c) = RemoteCertificatePinning.resolveServerTrustChallenge(challenge)
        completionHandler(d, c)
    }
}
""",
    )
    assert not scan(tmp_path)


def test_flags_wkwebview_bare_typealias_signature(tmp_path: Path) -> None:
    """The bare typealias does not carry @MainActor @Sendable (#2608)."""
    _write(
        tmp_path,
        "Views/V.swift",
        """final class C: NSObject, WKNavigationDelegate {
    func webView(
        _ webView: WKWebView,
        didReceive challenge: URLAuthenticationChallenge,
        completionHandler: URLAuthenticationChallengeCompletionHandler
    ) {}
}
""",
    )
    assert scan(tmp_path)


def test_comment_not_flagged(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Views/V.swift",
        "// the old code used URLSession.shared here\nText(\"hi\")\n",
    )
    assert not scan(tmp_path)


def test_preview_block_not_flagged(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "Views/V.swift",
        "#Preview {\n  let _ = URLSession.shared\n}\n",
    )
    assert not scan(tmp_path)


def test_repo_has_no_new_transport_violations() -> None:
    found = scan()
    known = set(_mod.KNOWN_VIOLATIONS)
    new = set(found) - known
    assert not new, (
        "New Swift transport/TLS violation(s) (#2606 / #2608):\n"
        + "\n".join(f"  {k}: {found[k]}" for k in sorted(new))
    )


def test_transport_known_violations_are_not_stale() -> None:
    found = scan()
    stale = set(_mod.KNOWN_VIOLATIONS) - set(found)
    assert not stale, (
        f"Stale KNOWN_VIOLATIONS entries (site fixed — remove them): {stale}"
    )
