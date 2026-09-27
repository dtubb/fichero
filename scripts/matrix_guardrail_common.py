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
_SWIFT_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)


def strip_swift_comments(text: str) -> str:
    """Swift source with its comments removed, so prose cannot stand in for a call.

    These matrices ask "does the app REACH this endpoint", and answered it by looking for
    the path string in the file text. A doc comment naming a path satisfies that. Measured
    2026-09-27 on check_endpoint_coverage_matrix: of 284 endpoints whose path appeared in
    Swift, only 104 appeared in code — 180 were witnessed by a comment alone, among them
    `POST /api/segments/passes`, which is the same false "adopted" claim #5105 records.

    Whole-line `//` and `///` comments go, and so do `/* */` blocks. A trailing comment on
    a code line is left alone: the code beside it is the part that matters, and dropping the
    tail would mean parsing string literals to know where the comment really starts.
    """
    text = _SWIFT_BLOCK_COMMENT_RE.sub(" ", text)
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("//")
    )


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


def normalize_source(text: str) -> str:
    r"""Normalise SOURCE so its paths compare against `normalize_path` output — and no more.

    `normalize_text` exists for OpenAPI paths, and collapses `{anything}` to `{}` so
    `/documents/{document_id}` and `/documents/{doc_id}` are one shape. Run over Swift, that
    regex eats code: `{[^{}]*}` matches every innermost brace block, so a single-statement
    function body disappears entirely —

        func f() -> Data { try await endpointData(path: "/api/kg/pykeen/reviews") }
        becomes
        func f() -> Data {}

    which is how `POST /api/kg/pykeen/reviews` read as unreached while two functions call it
    (2026-09-27). Only bodies that happened to contain a nested brace survived, which is why
    the `/reviews/{}` sibling was found and the bare `/reviews` was not.

    The template collapse is not needed on this side: Swift interpolation `\(id)` is already
    rewritten to `{}` above, which is the shape the OpenAPI side normalises to.

    `read_normalized_blob` still uses `normalize_text` and so still has this defect for every
    caller that passes it Swift (#5108 names check_undo_coverage). Those guards each carry a
    seeded baseline measured through the defect, so they are fixed one at a time with their
    baselines re-reviewed, not swept.
    """
    text = _SWIFT_INTERPOLATION_RE.sub("{}", text)
    text = text.replace("/api/", "/")
    return _WHITESPACE_RE.sub(" ", text).strip()


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


_SWIFT_STRING_ARRAY_RE = re.compile(r'\[\s*("(?:[^"\\\n]+)"(?:\s*,\s*"(?:[^"\\\n]+)")*)\s*,?\s*\]')
_QUOTED_RE = re.compile(r'"([^"]*)"')


def expand_swift_path_components(text: str) -> str:
    """Append the slash-joined form of every Swift array of string literals.

    A third way the app names an endpoint, after the generated operation name and a literal
    path: `client.streamLines(pathComponents: ["activity", "stream"])`. The SSE consumers dial
    this way because a stream cannot go through the generated client, and the path exists only
    as its segments — so a matcher looking for `/activity/stream` finds nothing, and the
    endpoint reads as unreached. Found 2026-09-27 when stripping comments stopped a doc comment
    in ActivityStreamService from covering for the real call.

    Appended rather than substituted: the array may be any list of strings, and the reassembled
    path is an extra thing to match against, never a claim about what the array meant.
    """
    # Emitted QUOTED, because `dialled_paths` reads whole string literals: an unquoted
    # reassembled path would be invisible to it and the SSE streams would read as unreached.
    extras = [
        '"/' + "/".join(_QUOTED_RE.findall(match.group(1))) + '"'
        for match in _SWIFT_STRING_ARRAY_RE.finditer(text)
    ]
    return text + "\n" + "\n".join(extras) if extras else text


def read_swift_code_blob(paths: list[Path]) -> str:
    """`read_normalized_blob`, minus the comments, plus reassembled path-component arrays.

    Use this for any "is this endpoint reached" answer. `read_normalized_blob` reads raw file
    text, where a `///` line naming a path counts as calling it.
    """
    chunks: list[str] = []
    for path in sorted(paths):
        try:
            body = strip_swift_comments(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        chunks.append(normalize_source(expand_swift_path_components(body)))
    return "\n".join(chunks)


def swift_operation_name(operation_id: str) -> str:
    """The generated Swift client's method name for an OpenAPI operationId.

    The house rule forbids hand-rolled URLs, so nearly every call goes through the generated
    client and the path string never appears in Swift at all. The operation name is therefore
    the primary witness, not a special case: adding it to check_endpoint_coverage_matrix made
    all ten of that guard's hand-written witness-table entries redundant at once (2026-09-27).
    """
    parts = [part for part in operation_id.split("_") if part]
    if not parts:
        return ""
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def path_is_dialled(normalized_path: str, blob: str) -> bool:
    """Whether `blob` dials exactly this path, and not a longer one that starts with it.

    `normalize_text` strips the `/api/` prefix, which makes short paths substrings of longer
    siblings: `POST /api/links` becomes `/links`, so a plain `in` test reports it reached
    wherever `/links/types` or `/links/of/{}` appears. Found 2026-09-27 while triaging this
    guard — the substring hit was inflating the count of endpoints that looked wired.

    A real dial ends the path: a quote, a `?`, a paren, end of line — never another segment or
    more of the same word. It BEGINS somewhere a string or an argument begins, which has to be
    a whitelist rather than "not a word character": `/links` is a suffix of
    `/claims/{}/links`, so the character before it is `}`, which is legal inside a path. Both
    ends were needed — prose "bold/italic/inline code/links" matched from the left, and the
    longer sibling matched from the right, and both were reporting `POST /api/links` as wired
    when nothing calls it (2026-09-27).
    """
    return re.search(
        rf"(?:^|(?<=[\s\"'`(,=:\[])){re.escape(normalized_path)}(?![A-Za-z0-9_/-])",
        blob,
    ) is not None


_PATH_LITERAL_RE = re.compile(r'"(/[^"\s]*)"')
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def dialled_paths(blob: str) -> frozenset[str]:
    """Every path the source actually dials, as a set of whole tokens.

    This replaces asking `is this path a substring of the file` 742 times over a 10 MB blob —
    which was both slow (the check became the guardrail suite's bottleneck) and the source of
    the boundary problems: `/links` is a substring of `/links/types`, of `/claims/{}/links`,
    and of the prose "inline code/links". Extracting whole string literals removes the question
    instead of answering it more carefully, and turns 742 scans into one.

    A query string is dropped and a trailing slash is normalised away, so `"/search?q={}"` and
    `"/search/"` both answer for `/search`.
    """
    found: set[str] = set()
    for literal in _PATH_LITERAL_RE.findall(blob):
        token = literal.split("?", 1)[0]
        found.add(token)
        found.add(token.rstrip("/") or "/")
    return frozenset(found)


def source_identifiers(blob: str) -> frozenset[str]:
    """Every identifier in the source, so an operation-name lookup is a set membership test."""
    return frozenset(_IDENTIFIER_RE.findall(blob))


def endpoint_key(method: str, path: str) -> str:
    return f"{method.upper()} {path}"

