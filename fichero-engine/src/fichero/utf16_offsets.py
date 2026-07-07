"""UTF-16 ↔ code-point offset conversion for annotation anchors (#3262).

The Swift frontend captures and renders char offsets as UTF-16 (NSString /
NSRange / String.Index(utf16Offset:)). Python ``str[i:j]`` slices by code
point. For text containing characters outside the BMP (emoji, some
math/symbol chars in transcriptions), every offset past the first such
character is silently wrong — a 2-unit surrogate pair shifts all
subsequent offsets by +1 per non-BMP character.

The canonical contract: ``char_start`` / ``char_end`` on Annotation and
KnowledgeClaim are **UTF-16 offsets** (what the frontend sends). The
backend converts them to Python code-point offsets before slicing
``page_content``. This module provides the conversion helper.
"""


def utf16_offset_to_codepoint(text: str, utf16_offset: int) -> int:
    """Convert a UTF-16 offset to a Python code-point offset.

    Iterates through the string, accumulating the UTF-16 length of each
    code point (1 for BMP, 2 for supplementary), and returns the code-point
    index where the cumulative UTF-16 length reaches or exceeds ``utf16_offset``.

    If ``utf16_offset`` exceeds the UTF-16 length of ``text``, returns
    ``len(text)`` (clamped to end of string).
    """
    cp_offset = 0
    utf16_so_far = 0
    for char in text:
        # Supplementary plane characters (emoji, rare CJK, etc.) are 2 UTF-16
        # code units (a surrogate pair). BMP characters are 1.
        char_utf16_len = 2 if ord(char) > 0xFFFF else 1
        if utf16_so_far + char_utf16_len > utf16_offset:
            # The offset lands inside this character — snap to its start.
            break
        utf16_so_far += char_utf16_len
        cp_offset += 1
    return cp_offset


def utf16_range_to_codepoint_range(text: str, utf16_start: int, utf16_end: int) -> tuple[int, int]:
    """Convert a UTF-16 (start, end) pair to Python code-point (start, end).

    Clamp both ends to ``[0, len(text)]``. If start >= end after
    conversion, returns (0, 0) — the caller should treat this as empty.
    """
    cp_start = utf16_offset_to_codepoint(text, utf16_start)
    cp_end = utf16_offset_to_codepoint(text, utf16_end)
    if cp_start >= cp_end:
        return (0, 0)
    return (cp_start, cp_end)
