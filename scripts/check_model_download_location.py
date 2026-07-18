#!/usr/bin/env python3
"""Shared model-download-location guardrail (§6b reform master plan).

Rule (one canonical models folder):

    > Every locally-downloaded model (FastEmbed/HuggingFace embeddings, Whisper,
    > spaCy, hf_hub/snapshot downloads) must land in the ONE shared models
    > folder — `engine_state_dir() / "models"` — not in a per-library, scattered,
    > or auto-cleaned (`~/.cache`) location, and not under a stale bundle id.

The canonical shared folder is defined in `fichero/paths.py`:

    engine_state_dir() / "models"   →   ~/Library/Application Support/Fichero/models

This guardrail performs static analysis over the backend source (it does NOT
download anything). It enforces two things:

  (A) Every `MODELS_BASE = …` definition must DERIVE from `engine_state_dir()`
      (so all callers resolve to the same shared folder). A hardcoded path —
      e.g. a literal `~/Library/Application Support/com.fichero.fichero/models`
      — is a divergence: it points models at a DIFFERENT folder than the rest of
      the engine.

  (B) Every model-download PATH DECISION — an assignment to `cache_dir`,
      `download_root`, `local_dir`, `model_cache_dir`, or `models_dir`, and any
      `snapshot_download(...)` / `hf_hub_download(...)` call — must reference a
      canonical path token (`MODELS_BASE`, `engine_state_dir`, or one of the
      `*_path` attributes that hang off it). A literal/absolute/`.cache` path is
      a violation.

KNOWN_VIOLATIONS is the current divergence backlog, keyed by content hash (never
a line number). It PASSES today and FAILS when a NEW download escapes the shared
folder. The single current divergence — `audio_base.py`'s `MODELS_BASE` pointing
at the legacy `com.fichero.fichero` bundle dir instead of
`engine_state_dir()/"models"` — is baselined and noted below.

Usage:
    scripts/check_model_download_location.py
    scripts/check_model_download_location.py --list
    scripts/check_model_download_location.py --help

Exit codes:
    0  every download path is canonical or in KNOWN_VIOLATIONS
    1  a new divergent download path appeared, or a known entry is stale
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE_SRC = ROOT / "fichero-engine" / "src" / "fichero"
RULE_DOC = "docs/contributor/architecture/fichero/reform_masterplan_2026-06.md"

# The canonical shared models folder, as defined in fichero/paths.py.
CANONICAL_MODELS_DIR_EXPR = 'engine_state_dir() / "models"'

# Tokens that prove a path derives from the shared models folder.
CANONICAL_TOKENS = (
    "MODELS_BASE",
    "engine_state_dir",
    "whisper_path",
    "embeddings_path",
    "spacy_path",
    "base_path",
    "models_path",
)

# Assignment targets that DECIDE a model-download path.
_PATH_ASSIGN_RE = re.compile(
    r"^\s*(cache_dir|download_root|local_dir|model_cache_dir|models_dir)\s*=\s*(.+)$"
)
_MODELS_BASE_RE = re.compile(r"\bMODELS_BASE\s*=")
_HF_DOWNLOAD_RE = re.compile(r"\b(snapshot_download|hf_hub_download)\s*\(")
_LINE_COMMENT = re.compile(r"#.*")

# A right-hand side only DECIDES a path if it builds one (literal, join, Path,
# expanduser, …). A bare `cache_dir=cache_dir,` kwarg passthrough does NOT.
_PATH_EXPR_RE = re.compile(
    r"""/|Path\(|str\(|["']|expanduser|tempfile|os\.path|\.home\(\)|\.cache"""
)

# Current divergence backlog (content-hash keyed). Empty: every model-download
# path now derives from engine_state_dir()/"models" — audio_base.py Whisper was
# the last divergence (legacy bundle dir), fixed in #2269.
KNOWN_VIOLATIONS: dict[str, str] = {}


def _key(rel: str, snippet: str) -> str:
    normalized = re.sub(r"\s+", " ", snippet.strip())
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
    return f"{rel}#{digest}"


def _has_canonical_token(text: str) -> bool:
    return any(tok in text for tok in CANONICAL_TOKENS)


def _models_base_window(source: str, start: int) -> str:
    """Grab the RHS of a `MODELS_BASE = …` definition (may span parens)."""
    window = source[start : start + 240]
    # Stop at a blank line / comment banner so we don't slurp the next statement.
    window = window.split("\n\n")[0]
    return re.sub(r"\s+", " ", window).strip()


def scan(engine_src: Path = ENGINE_SRC) -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(engine_src.rglob("*.py")):
        if "tests" in path.parts or "generated" in path.parts:
            continue
        try:
            source = path.read_text(errors="ignore")
        except OSError:
            continue
        rel = path.relative_to(engine_src).as_posix()

        # (A) MODELS_BASE definitions must derive from engine_state_dir().
        for m in _MODELS_BASE_RE.finditer(source):
            window = _models_base_window(source, m.start())
            if "engine_state_dir" not in window:
                found[_key(rel, window)] = (
                    f"MODELS_BASE does not derive from engine_state_dir(): {window}"
                )

        # (B) Per-line download path decisions.
        for idx, raw in enumerate(source.splitlines()):
            line = _LINE_COMMENT.sub("", raw)
            am = _PATH_ASSIGN_RE.match(line)
            if (
                am
                and _PATH_EXPR_RE.search(am.group(2))
                and not _has_canonical_token(am.group(2))
            ):
                found[_key(rel, line)] = (
                    f"{am.group(1)} assigned a non-canonical path (line {idx + 1}): "
                    f"{am.group(2).strip()}"
                )
            if _HF_DOWNLOAD_RE.search(line) and not _has_canonical_token(line):
                found[_key(rel, line)] = (
                    f"hf download call without a shared-folder path (line {idx + 1})"
                )
    return found


def main() -> int:
    if any(arg in ("-h", "--help") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    found = scan()
    known = set(KNOWN_VIOLATIONS)

    if "--list" in sys.argv[1:]:
        print(f"Model-download path sites ({len(found)} divergence(s)):\n")
        for key, reason in sorted(found.items()):
            tag = "known" if key in known else "NEW"
            print(f"  [{tag}] {key}\n         {reason}")
        return 0

    new = sorted(set(found) - known)
    stale = sorted(known - set(found))

    print(f"Model-download location guardrail: scanned {ENGINE_SRC.relative_to(ROOT)}")
    print(f"  canonical shared folder: {CANONICAL_MODELS_DIR_EXPR}")
    print(f"  {len(found)} divergence(s); {len(known)} known.")

    if stale:
        print(f"\n  ✓ {len(stale)} KNOWN_VIOLATIONS entry now clean — drop from the set:")
        for key in stale:
            print(f"      {key}")

    if new:
        print(f"\n  ✗ {len(new)} new model-download path escaping the shared folder:")
        for key in new:
            print(f"      {key}\n          ←  {found[key]}")
        print(
            f"\nFix: derive the path from `{CANONICAL_MODELS_DIR_EXPR}` (via MODELS_BASE "
            "or a *_path attribute). If genuinely intentional, add to KNOWN_VIOLATIONS "
            f"with a reason. Rule: {RULE_DOC} §6b."
        )
        return 1

    if stale:
        print("\n(KNOWN_VIOLATIONS has stale entries — clean them up when convenient.)")
        return 1

    print("\n✓ Every model download targets the shared models folder.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
