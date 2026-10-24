"""Work the language and script out from the project's sample pages (`source.onboard.project.about-material`, Test 13).

"Not sure" is sent as the language `und` with no script. The engine then reads the sample pages (the page's own text where it
has some, else a quick read on this Mac), finds the script by the letters' Unicode blocks and the language by its function words,
and says so: the assembled recipe carries `inferred_language` (`code`, `name`, `script`, `from`, `sentence`) for the stage pages'
"worked out from your pages: Spanish; change it". The person confirms; nothing is saved by this module. When the pages do not say,
the field says that, and the plan is made with the language unknown (Kraken's blla finds lines for any script; readers are ranked
with what is known).
"""
from __future__ import annotations

import logging
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: The answer "Not sure" is sent as (BCP 47's undetermined language).
UNSURE = "und"
#: Sample pages looked at, and the least letters that make a reading worth believing.
MAX_PAGES, MIN_LETTERS = 3, 40
#: A language wins on this many function words, this many times the next one's.
MIN_HITS, MIN_RATIO = 4, 1.5

#: Unicode name prefix -> ISO 15924 code, for the scripts a project of ours is likely to hold.
_SCRIPTS = {"LATIN": "Latn", "CYRILLIC": "Cyrl", "GREEK": "Grek", "ARABIC": "Arab", "HEBREW": "Hebr", "CJK": "Hani",
            "HIRAGANA": "Hira", "KATAKANA": "Kana", "HANGUL": "Hang", "DEVANAGARI": "Deva", "ETHIOPIC": "Ethi",
            "CANADIAN": "Cans", "CHEROKEE": "Cher", "ARMENIAN": "Armn", "GEORGIAN": "Geor", "THAI": "Thai"}
#: The languages of a Latin-script archive, by their commonest function words.
_WORDS: dict[str, frozenset[str]] = {
    "es": frozenset("el la los las de del en que y a un una por con para se su sus es no al lo como mas pero este esta dicho dha".split()),
    "en": frozenset("the of and to in that is was for with on at by from this be are as not have it his her they".split()),
    "pt": frozenset("o a os as de do da dos das em que e um uma por com para se seu sua nao mais como foi".split()),
    "fr": frozenset("le la les de des du et en un une que qui dans pour par sur au aux est pas ce se son sa".split()),
    "it": frozenset("il lo la i gli le di del della dei e in un una che per con non si su da come più è".split()),
    "la": frozenset("et in est non ad cum de ex qui quae quod sed per ut ab pro sunt esse hoc".split()),
    "de": frozenset("der die das und in den von zu mit sich des auf für ist im dem nicht ein eine als auch".split()),
}


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold()) if not unicodedata.combining(c))


def script_of(text: str) -> str | None:
    """The script most of `text`'s letters are in (ISO 15924), or None when it has too few letters to say."""
    counts: Counter[str] = Counter()
    for ch in text:
        if ch.isalpha():
            code = _SCRIPTS.get(unicodedata.name(ch, "").split(" ", 1)[0])
            if code:
                counts[code] += 1
    total = sum(counts.values())
    if total < MIN_LETTERS:
        return None
    code, n = counts.most_common(1)[0]
    return code if n * 2 > total else None


def language_of(text: str) -> str | None:
    """The language tag whose function words `text` uses clearly more than any other's, or None."""
    words = re.findall(r"[^\W\d_]+", _fold(text))
    hits = {tag: sum(1 for w in words if _fold(w) in vocab) for tag, vocab in _WORDS.items()}
    ranked = sorted(hits.items(), key=lambda kv: -kv[1])
    (best, n), (_other, m) = ranked[0], ranked[1]
    return best if n >= MIN_HITS and n >= m * MIN_RATIO else None


def _page_text(db: Any, library: Path, doc: Any) -> str:
    """The page's own text, else a quick read of its picture on this Mac (Apple Vision, when this Mac has it); '' when neither."""
    text = (getattr(doc, "page_content", None) or "").strip()
    if text:
        return text
    raw = getattr(doc, "path", None)
    if not raw:
        return ""
    path = Path(raw) if Path(raw).is_absolute() else library / raw
    try:
        from fichero_server.training.evaluation import apple_vision_here
        from fichero_server.workflows.tools.vision_base import apple_vision_ocr

        if path.suffix.lower() == ".pdf" or not path.is_file() or not apple_vision_here():
            return ""
        # "auto": no language is assumed, the question is which it is
        return (apple_vision_ocr(str(path), "auto") or "").strip()
    except Exception as exc:  # noqa: BLE001 -- a quick read that cannot run says nothing; the field then says "could not tell"
        logger.info("language guess: the quick read of %s did not run: %s", path.name, exc)
        return ""


def unsure(answers: dict[str, Any]) -> bool:
    """Whether the answers say "Not sure": the language is `und` (alone) and no script is given."""
    languages = answers.get("languages") or []
    return list(languages) == [UNSURE] and not answers.get("scripts")


#: The guess kept per project and sample-page set (a quick read of three pages is not repeated on every assemble); it changes
#: when the samples do (a different page set, or a page's text edited, `updated_at`). Memory only: a restart reads again.
_KEPT: dict[tuple, dict[str, Any]] = {}


def infer(db: Any, library: Path) -> dict[str, Any]:
    """`{code, name, script, from, sentence}` for the sample pages; `code` and `script` are None where the pages do not say.
    Blocking (a quick read runs OCR): callers on the event loop run it in a thread."""
    from fichero_server.models import Document
    from fichero_server.recipes import samples

    pages = [p["id"] for p in samples._chosen(db)["pages"]][:MAX_PAGES]
    docs = [d for i in pages if (d := db.get(Document, i)) is not None]
    key = (str(library), *((d.id, str(getattr(d, "updated_at", ""))) for d in docs))
    if key not in _KEPT:
        _KEPT.clear()  # one project's guess at a time: the samples of an older set are not coming back
        _KEPT[key] = _guess(db, library, docs)
    return dict(_KEPT[key])


def _guess(db: Any, library: Path, docs: list[Any]) -> dict[str, Any]:
    from fichero_server.recipes.names import language_name, script_name

    text = "\n".join(_page_text(db, library, d) for d in docs)
    script, code = script_of(text), language_of(text)
    if code and not script:
        script = "Latn" if code in _WORDS else None
    if code is None and script is None:
        return {"code": None, "name": None, "script": None, "from": "pages",
                "sentence": "Could not tell the language from your pages: choose it to get readers ranked for it."}
    name = language_name(code) if code else None
    written = script_name(script) if script else None
    said = " ".join(x for x in (name, f"in the {written} script" if written else None) if x) if name else f"the {written} script"
    return {"code": code, "name": name, "script": script, "from": "pages",
            "sentence": f"Language worked out from your pages: {said}. Change it if that is wrong."}
