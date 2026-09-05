"""Apple's on-device translator, through the existing fm-bridge subprocess.

Translation is a DIFFERENT framework from FoundationModels: it needs no Apple
Intelligence, no model assets, and works on machines where the on-device LLM
is unavailable. It rides the same bridge binary anyway (`fm-bridge
--translate`) because the seam already exists — one binary to find, one
protocol to parse, one thing to ship. `TranslationSession` has a headless
initializer (`installedSource:target:`), which is what makes this possible at
all; the framework is otherwise usually reached through a SwiftUI modifier.

Two rules this module exists to keep:

- **A missing language pack is a refusal, not a fallback.** macOS can only
  download a translation model through its own UI, which a CLI cannot present.
  So an uninstalled pair raises :class:`TranslationModelNotInstalledError`
  naming the pair. Returning the source text unchanged — or quietly routing to
  a paid LLM — would be the app claiming to have translated something it did
  not.
- **The source language is the caller's to state.** The headless session takes
  a concrete source language, and the engine already detects it
  (``llm.lang_detect``). Guessing here would put a second, weaker detector in
  the stack.

Nothing here is wired into the ``translate`` tool yet: the program says a
3-page real-data spot-check against the LLM step comes first.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Bridge exit shapes this module gives a name to. Everything else arrives as
#: a plain :class:`TranslationBridgeError` carrying the bridge's own kind.
KIND_NOT_INSTALLED = "not_installed"
KIND_UNSUPPORTED_PAIR = "unsupported_pair"

DEFAULT_TIMEOUT_SECONDS = 120.0


class TranslationBridgeError(RuntimeError):
    """A translation the bridge declined to perform, with its reason kind."""

    def __init__(self, message: str, *, kind: str) -> None:
        super().__init__(message)
        self.kind = kind


class TranslationModelNotInstalledError(TranslationBridgeError):
    """The pair is supported but its model is not downloaded on this Mac.

    Typed on purpose: the caller's only useful response is to ask the USER to
    install the pair (macOS shows that sheet, not us). A caller that cannot do
    that must surface the refusal — never substitute another translator
    silently, which would change what the archive says without saying so.
    """


class TranslationPairUnsupportedError(TranslationBridgeError):
    """macOS does not translate between these two languages at all."""


def build_translate_request(
    texts: list[str], *, source: str, target: str
) -> dict[str, Any]:
    """The bridge's stdin payload for a batch translation.

    Empty strings are kept in place: the response is positional, and dropping
    one would silently shift every translation after it onto the wrong text.
    """
    if not texts:
        raise ValueError("translate needs at least one text")
    source = (source or "").strip()
    target = (target or "").strip()
    if not source:
        raise ValueError(
            "translate needs a concrete source language — detect it before "
            "calling (llm.lang_detect), do not guess in the bridge"
        )
    if not target:
        raise ValueError("translate needs a target language")
    return {"source": source, "target": target, "texts": list(texts)}


def parse_translate_response(stdout: bytes, *, expected: int) -> list[str]:
    """The bridge's stdout payload as translations, positionally verified.

    The count check is the point: a batch that came back short would otherwise
    pair translations with the wrong sources from the shortfall onward, and
    every downstream artifact would carry a plausible, wrong translation.
    """
    try:
        payload = json.loads(stdout.decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TranslationBridgeError(
            f"fm-bridge --translate stdout was not valid JSON: {stdout!r}",
            kind="json",
        ) from exc

    translations = payload.get("translations")
    if not isinstance(translations, list) or not all(
        isinstance(item, str) for item in translations
    ):
        raise TranslationBridgeError(
            f"fm-bridge --translate returned no translations array: {payload!r}",
            kind="json",
        )
    if len(translations) != expected:
        raise TranslationBridgeError(
            f"fm-bridge --translate returned {len(translations)} translations "
            f"for {expected} texts — refusing to pair them up",
            kind="json",
        )
    return translations


def raise_from_translate_stderr(stderr: bytes, returncode: int) -> None:
    """Turn the bridge's typed error payload into a typed Python error."""
    text = stderr.decode(errors="replace")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        raise TranslationBridgeError(
            f"fm-bridge --translate exited {returncode}: {text}", kind="error"
        ) from None

    kind = payload.get("kind", "error")
    message = payload.get("error", text)
    if kind == KIND_NOT_INSTALLED:
        raise TranslationModelNotInstalledError(message, kind=kind)
    if kind == KIND_UNSUPPORTED_PAIR:
        raise TranslationPairUnsupportedError(message, kind=kind)
    raise TranslationBridgeError(message, kind=kind)


async def translate_texts(
    texts: list[str],
    *,
    source: str,
    target: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[str]:
    """Translate a batch on-device. Free, offline, and it never guesses.

    Raises rather than degrading: see the module docstring.
    """
    from fichero_server.llm import _find_fm_bridge_binary

    request = build_translate_request(texts, source=source, target=target)
    binary = _find_fm_bridge_binary()
    if binary is None:
        raise TranslationBridgeError(
            "fm-bridge binary not found. Build it with "
            "fichero-server/scripts/build_fm_bridge.sh",
            kind="unavailable",
        )

    proc = await asyncio.create_subprocess_exec(
        str(binary),
        "--translate",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(json.dumps(request).encode()), timeout=timeout
        )
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise TranslationBridgeError(
            f"fm-bridge --translate exceeded {timeout}s for {len(texts)} text(s)",
            kind="timeout",
        ) from None

    if proc.returncode != 0:
        raise_from_translate_stderr(stderr, proc.returncode or 1)
    return parse_translate_response(stdout, expected=len(texts))
