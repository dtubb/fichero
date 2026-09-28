"""A plain-text transcription beside its page image (#5174, ruled 2026-09-28).

"A same-named .txt beside an image becomes that page's transcription on import (one reading, no
boxes)." The whole file is ONE reading on ONE segment with no shape: the file says the text is on
this page and nothing about where, so the import anchors it to the page and marks it
`shape: unstated`, exactly as a text-only TEI line (`format_import._anchor_for`).

Never sniffed: prose looks like nothing, and a `.txt` is not guessed from its extension
(`test_harness.py::test_a_file_every_sniff_refuses_is_not_guessed_from_its_extension`). The
folder pairing names this format only for a `.txt` whose stem is an image's beside it; one file
can be forced with `--format plain-text`.

Read only: exporting a page as plain text is not asked for.
"""

from __future__ import annotations

from fichero_server.formats import FormatSpec, SourcePage, register
from fichero_server.formats.harness import PageSegment


def read(data: bytes) -> SourcePage:
    text = data.decode("utf-8-sig").strip()
    page = SourcePage(producer="plain-text transcription")
    if text:
        page.segments.append(PageSegment(kind="region", readings=[("transcription", text)], ref="text"))
    return page


register(
    FormatSpec(
        name="plain-text",
        # No extension: `format_for` must never pick it (see the module docstring).
        extensions=(),
        read=read,
        write=None,
        schema=None,
        round_trips=False,
        sniff=lambda _data: False,
    )
)
