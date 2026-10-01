"""Which words a person's edit of their line took out (#5190).

`source.textedit.word-spans-in-the-line` and `source.textedit.a-word-leaves-the-line`. PURE, like
`resolve_counting`: no database, nothing stored -- the mapping is worked out from the words'
readings and the line's readings every time it is asked, so a stored copy could never go stale.

The words' readings joined with single spaces, in text order, are where every word starts: each
holds a run of those tokens. Each line reading in the correction chain, oldest first, is then
aligned token by token against the text before it (``difflib.SequenceMatcher(autojunk=False)``,
the alignment `views.diff_word_tokens` uses). A word stays only while its whole run falls in an
``equal`` run; anything else -- deleted, changed by one letter, moved, split or joined -- and it
has left. Tokens are compared after NFC and nothing else: "ſ" is not "s". Whitespace never counts.
Logical order throughout, so no direction or script needs a case of its own.

ponytail: runs are token indices, not the spec's UTF-16 offsets; nothing reads the offsets yet.
Convert with `core/utf16_offsets.py` when a caller needs them.
"""

from __future__ import annotations

import difflib
import unicodedata
from collections.abc import Sequence


def _tokens(text: str) -> list[str]:
    return unicodedata.normalize("NFC", text).split()


def words_that_leave(words: Sequence[tuple[str, str]], chain: Sequence[str]) -> set[str]:
    """The ids of the words that are no longer in the line.

    ``words``: ``(word_id, text)`` of each word WITH a counting reading, in text order.
    ``chain``: the texts of the line's readings the edit builds on, oldest first, ending with the
    reading that counts. An empty chain leaves nothing.
    """
    runs: dict[str, tuple[int, int]] = {}
    tokens: list[str] = []
    for word_id, text in words:
        start = len(tokens)
        tokens.extend(_tokens(text))
        if len(tokens) > start:
            runs[word_id] = (start, len(tokens))
    left = {word_id for word_id, _text in words if word_id not in runs}  # empty: nothing to keep

    for text in chain:
        new_tokens = _tokens(text)
        moved_to: dict[int, int] = {}
        matcher = difflib.SequenceMatcher(None, tokens, new_tokens, autojunk=False)
        for tag, i1, i2, j1, _j2 in matcher.get_opcodes():
            if tag == "equal":
                moved_to.update({i1 + k: j1 + k for k in range(i2 - i1)})
        for word_id, (start, end) in list(runs.items()):
            new = [moved_to.get(i) for i in range(start, end)]
            if None in new or new != list(range(new[0], new[0] + len(new))):
                left.add(word_id)
                del runs[word_id]
            else:
                runs[word_id] = (new[0], new[-1] + 1)
        tokens = new_tokens
    return left
