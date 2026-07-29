from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OPENAPI_CANDIDATES = (
    ROOT / "fichero-server" / "openapi.json",
    ROOT / "fichero" / "fichero-api-client" / "openapi.json",
    ROOT / "fichero-server" / "tests" / "contracts" / "openapi.json",
    ROOT / "fichero" / "fichero-api-client" / "Sources" / "FicheroAPIClient" / "openapi.json",
    ROOT / "fichero" / "fichero-api-client" / "Sources" / "openapi.json",
)
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}

_SWIFT_INTERPOLATION_RE = re.compile(r"\\\([^)]*\)")
_OPENAPI_TEMPLATE_RE = re.compile(r"\{[^{}]*\}")
_WHITESPACE_RE = re.compile(r"\s+")


def load_openapi() -> tuple[Path, dict[str, Any]]:
    for candidate in OPENAPI_CANDIDATES:
        if candidate.exists():
            return candidate, json.loads(candidate.read_text(encoding="utf-8"))
    searched = "\n  ".join(str(path.relative_to(ROOT)) for path in OPENAPI_CANDIDATES)
    raise FileNotFoundError(f"OpenAPI schema not found. Searched:\n  {searched}")


def normalize_text(text: str) -> str:
    text = _SWIFT_INTERPOLATION_RE.sub("{}", text)
    text = text.replace("/api/", "/")
    text = _OPENAPI_TEMPLATE_RE.sub("{}", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def normalize_path(path: str) -> str:
    return normalize_text(path)


def load_known_gaps(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"Expected object mapping in {path}")
    return {str(key): str(value) for key, value in data.items()}


def read_normalized_blob(paths: list[Path]) -> str:
    chunks: list[str] = []
    for path in sorted(paths):
        try:
            chunks.append(normalize_text(path.read_text(encoding="utf-8", errors="ignore")))
        except OSError:
            continue
    return "\n".join(chunks)


def endpoint_key(method: str, path: str) -> str:
    return f"{method.upper()} {path}"

