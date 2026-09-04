"""RTF → plain text, with no heavy loader dependencies.

Extracted from ``document_loader`` (#4666) so that every boundary which must
hand prose to a model — not just the file-import path — can reach the same
converter without dragging Kreuzberg/pdfium into its import graph.

``document_loader`` re-exports these names, so existing callers and tests are
unaffected.
"""

from __future__ import annotations

import re
import unicodedata

# RTF header groups whose content should be discarded (they're tables/metadata,
# not body text).  Keys must be lowercase control words.
_RTF_SKIP_GROUP_WORDS = frozenset(
    {
        "fonttbl", "colortbl", "stylesheet", "info", "pict", "shppict",
        "wshad", "filetbl", "listtable", "listoverridetable",
    }
)

# Matches RTF hex-escape sequences: \'XX where XX are two hex digits.
_RTF_HEX_FULL_RE = re.compile(r"\\'([0-9a-fA-F]{2})")
_RTF_HEX_RUN_RE = re.compile(r"(?:\\'[0-9a-fA-F]{2})+")
_RTF_UNICODE_RE = re.compile(r"\\u(-?\d+)\?")


def _looks_like_text(text: str, *, min_printable_ratio: float = 0.9) -> bool:
    """Whether a converter's output is prose rather than echoed binary.

    macOS ``textutil`` treats input it cannot parse as plain text and echoes
    the raw bytes, so a corrupt .doc "succeeds" with a screenful of NULs
    (#4215). Accepting that would substitute garbage for a real failure.
    """
    if not text or "\x00" in text:
        return False
    printable = sum(1 for ch in text if ch.isprintable() or ch in "\n\r\t")
    return printable / len(text) >= min_printable_ratio


def _decode_rtf_hex_byte(m: "re.Match[str]") -> str:
    """Decode a single RTF \'XX byte via cp1252 (Windows-1252 / Latin-1 superset)."""
    try:
        return bytes([int(m.group(1), 16)]).decode("cp1252")
    except (UnicodeDecodeError, ValueError):
        return m.group(0)


def _strip_rtf(text: str) -> str:
    """Convert raw RTF markup to plain text.

    Uses a character-by-character state machine so nested groups ({\fonttbl
    {\f0 Arial;}}) are handled correctly without a new dependency.  Returns
    the string unchanged when it doesn't look like RTF.
    """
    stripped = text.lstrip()
    if not stripped.startswith("{\\rtf"):
        return text

    # Decode \'XX hex escapes BEFORE the state machine strips control chars.
    # Without this, \'f3 (ó) becomes bare "f3" because the state machine
    # consumes ' as an unknown control symbol and outputs the hex digits as
    # plain text.  Only the full \'XX form is decoded; the bare 'XX form
    # (no backslash) is NOT decoded because it matches legitimate apostrophes
    # in plain text ("class of '92", "the '49ers") and corrupts them. (#2505)
    def _decode_unicode(match: "re.Match[str]") -> str:
        value = int(match.group(1))
        return chr(value if value >= 0 else value + 65536)

    stripped = _RTF_UNICODE_RE.sub(_decode_unicode, stripped)
    codepage = re.search(r"\\ansicpg(\d+)", stripped)
    encoding = f"cp{codepage.group(1)}" if codepage else "cp1252"

    def _decode_hex_run(match: "re.Match[str]") -> str:
        raw = bytes(int(value, 16) for value in _RTF_HEX_FULL_RE.findall(match.group()))
        try:
            return raw.decode(encoding)
        except LookupError:
            return raw.decode("cp1252", errors="replace")
        except UnicodeDecodeError:
            return raw.decode(encoding, errors="replace")

    stripped = _RTF_HEX_RUN_RE.sub(_decode_hex_run, stripped)

    output: list[str] = []
    # skip_until_depth > 0: skip content until depth drops below this value.
    # Set when a header-group control word (\fonttbl etc.) is encountered;
    # cleared when the matching closing } brings depth back below that level.
    skip_until_depth = 0
    depth = 0
    i = 0
    n = len(stripped)

    while i < n:
        ch = stripped[i]

        if ch == "{":
            depth += 1
            i += 1

        elif ch == "}":
            depth -= 1
            if skip_until_depth and depth < skip_until_depth:
                skip_until_depth = 0
            i += 1

        elif ch == "\\":
            i += 1
            if i >= n:
                break

            if stripped[i].isalpha():
                # Control word: \word[-N][ ]
                j = i
                while j < n and stripped[j].isalpha():
                    j += 1
                word = stripped[i:j].lower()
                i = j
                # Skip optional numeric parameter
                if i < n and (stripped[i].isdigit() or stripped[i] == "-"):
                    while i < n and stripped[i] in "0123456789-":
                        i += 1
                # Skip optional single space delimiter
                if i < n and stripped[i] == " ":
                    i += 1

                if skip_until_depth:
                    continue

                if word in _RTF_SKIP_GROUP_WORDS:
                    # depth already incremented by the preceding {;
                    # skip everything until depth drops below current level.
                    skip_until_depth = depth
                elif word in ("par", "pard", "sect", "page"):
                    output.append("\n")
                elif word == "line":
                    output.append("\n")
                elif word == "tab":
                    output.append("\t")
                # All other control words (font, size, bold…) are formatting — skip.

            else:
                # Control symbol (\\, \{, \}, \~, \-, …)
                sym = stripped[i]
                i += 1
                if not skip_until_depth:
                    if sym == "\\":
                        output.append("\\")
                    elif sym == "{":
                        output.append("{")
                    elif sym == "}":
                        output.append("}")
                    elif sym == "~":
                        output.append(" ")  # non-breaking space
                    elif sym == "-":
                        output.append("­")  # soft hyphen
                    elif sym in ("\n", "\r"):
                        # A backslash at end of line is how TextEdit writes a
                        # paragraph break. Ignoring it welded the last word of
                        # one line onto the first of the next: the manuscript's
                        # "ca\'f1istin\\<newline>estantes" reached the model as
                        # "cañistinestantes", a word no historian would
                        # recognise, and the extractor built claims out of it
                        # (#4666).
                        output.append("\n")
                    # Other control symbols are ignored

        else:
            if not skip_until_depth and depth >= 1:
                output.append(ch)
            i += 1

    result = "".join(output)
    result = re.sub(r" {2,}", " ", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


# ---------------------------------------------------------------------------
# Residual-escape repair (#4666)
# ---------------------------------------------------------------------------
#
# ``_strip_rtf`` only fires on a string that IS an RTF document (it must start
# with ``{\\rtf``). Text that merely CARRIES RTF hex escapes — a fragment
# pasted out of a rich-text editor, a model's echo of an RTF prompt, a claim
# already persisted from such a run — never reaches the decoder above and keeps
# the escapes verbatim: "se\\'f1or" instead of "señor".
#
# That is what a historian then reads in the SVO browser, and what a search for
# "señor" fails to match. Decoding the escape is not a display nicety; it is the
# difference between the archive holding the word and holding a byte code.


def decode_rtf_hex_escapes(text: str, *, encoding: str = "cp1252") -> str:
    """Decode residual ``\\'XX`` RTF byte escapes anywhere in ``text``.

    Runs of escapes are decoded together so multi-byte sequences (UTF-8 or a
    DBCS codepage written one byte per escape) round-trip. Only the full
    backslash form is decoded — the bare ``'XX`` form is left alone because it
    collides with legitimate apostrophes ("class of '92"). Unknown or
    undecodable bytes are returned unchanged rather than replaced, so nothing
    is silently corrupted.
    """
    if not text or "\\'" not in text:
        return text

    def _decode_run(match: "re.Match[str]") -> str:
        raw = bytes(int(value, 16) for value in _RTF_HEX_FULL_RE.findall(match.group()))
        # The DECLARED codepage decides, not a guess. RTF defines \\'XX as a
        # byte in the document's codepage, and cp1252 decodes nearly every
        # byte — so "sniffing" UTF-8 first would silently re-read a genuine
        # cp1252 pair as one character and change what the document says.
        # cp1252 is the last resort only for a codepage Python does not know.
        for candidate in (encoding, "cp1252"):
            try:
                return raw.decode(candidate)
            except (LookupError, UnicodeDecodeError):
                continue
        return match.group()

    return _RTF_HEX_RUN_RE.sub(_decode_run, text)


def to_plain_text(text: str) -> str:
    """Normalise any stored content string into prose fit for a model or a row.

    Three steps, each a no-op when it does not apply:
    1. full RTF documents are converted to text (``_strip_rtf``),
    2. residual ``\\'XX`` escapes are decoded,
    3. the result is NFC-normalised so "señor" has one byte sequence in the
       database and a search for it matches.
    """
    if not text:
        return text
    return unicodedata.normalize("NFC", decode_rtf_hex_escapes(_strip_rtf(text)))
