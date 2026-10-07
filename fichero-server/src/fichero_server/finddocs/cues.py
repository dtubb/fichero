"""The cues Find the Documents reads in a page's text, as one table (`finddocs.boundaries.proposed-with-evidence`).

The structure is language-agnostic: a cue is a row (its id, what it says, the pattern, its weight, where on
the page it counts, and the kind of document it suggests). Spanish and English rows to start; another
language adds rows, nothing else. Every row is tried on every page whatever its language: a Spanish court
caption on a page of an English bundle still says a document starts.

Weights are log-odds added to a prior (`propose.PRIOR`): an opening cue at the head of page n+1 and a
closing cue at the foot of page n make a boundary between them likely; a sentence running over the break
makes one unlikely. Rule weights, not a trained model: the project's own model replaces them once it has
examples (`finddocs.student-model`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Month names by language, for place-and-date lines and for reading a document's date.
MONTHS: dict[str, tuple[str, ...]] = {
    "es": ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
           "octubre", "noviembre", "diciembre"),
    "en": ("january", "february", "march", "april", "may", "june", "july", "august", "september",
           "october", "november", "december"),
}
_ES_MONTH = "|".join(MONTHS["es"]) + "|setiembre"
_EN_MONTH = "|".join(MONTHS["en"])
_PLACE = r"[A-ZÁÉÍÓÚÑ][\wáéíóúñ .'-]{1,40},\s*"


@dataclass(frozen=True)
class Cue:
    """One row of the table."""

    id: str
    #: opening (a document starts here), closing (one ends here), or kind (only names the kind).
    role: str
    language: str
    pattern: str
    weight: float
    #: head: the first lines of the page; tail: its last lines; any: anywhere on it.
    where: str = "head"
    #: The prototype this cue suggests for the document it opens or closes.
    kind: str | None = None
    flags: int = re.IGNORECASE | re.MULTILINE
    regex: re.Pattern = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "regex", re.compile(self.pattern, self.flags))


CUES: tuple[Cue, ...] = (
    # --- Spanish: openings -------------------------------------------------------------------------
    Cue("court-caption", "opening", "es", r"^\s*(JUZGADO|TRIBUNAL|CORTE|ALCALD[IÍ]A|INSPECCI[OÓ]N)\b", 2.0,
        flags=re.MULTILINE),
    Cue("judgment-vistos", "opening", "es", r"^\s*VISTOS\b", 2.5, kind="Sentencia", flags=re.MULTILINE),
    Cue("judgment-heading", "opening", "es", r"^\s*SENTENCIA\b", 2.5, kind="Sentencia", flags=re.MULTILINE),
    Cue("complaint-heading", "opening", "es", r"^\s*DEMANDA\b", 2.5, kind="Demanda", flags=re.MULTILINE),
    Cue("power-heading", "opening", "es", r"^\s*PODER\b", 2.5, kind="Poder", flags=re.MULTILINE),
    Cue("hearing-heading", "opening", "es", r"^\s*(ACTA DE AUDIENCIA|AUDIENCIA)\b", 2.5, kind="Acta de audiencia",
        flags=re.MULTILINE),
    Cue("letter-salutation", "opening", "es",
        r"^\s*(muy\s+)?(señor(a|es)?|sr(a)?\.|estimad[oa]s?|distinguid[oa]|apreciad[oa]|querid[oa])\b[^\n]{0,60}[:,]\s*$",
        2.5, kind="Carta"),
    Cue("cable-heading", "opening", "es", r"^\s*(TELEGRAMA|CABLEGRAMA|CABLE|RADIOGRAMA)\b", 3.0, kind="Cable"),
    Cue("receipt-heading", "opening", "es", r"^\s*(RECIBO\b|Rec[ií]b[ií]\b|Recibimos\b)", 2.5, kind="Recibo"),
    # "Istmina, 12 de marzo de 1948" or "Istmina, doce de marzo de mil novecientos cuarenta y ocho".
    Cue("place-and-date", "opening", "es",
        rf"^\s*({_PLACE})?(\d{{1,2}}|[a-záéíóúñ]+(\s+y\s+[a-záéíóúñ]+)?)\s+de\s+({_ES_MONTH})\s+de\s+"
        rf"(\d{{4}}|mil\s+[a-záéíóúñ ]+)\s*\.?\s*$", 1.5),
    # --- Spanish: closings -------------------------------------------------------------------------
    Cue("copy-and-notify", "closing", "es", r"\b(c[oó]piese|notif[ií]quese|publ[ií]quese|arch[ií]vese)\b", 2.0,
        where="tail", kind="Sentencia"),
    Cue("typed-signature", "closing", "es", r"\(\s*fdo\.?\s*\)", 1.0, where="tail"),
    Cue("letter-closing", "closing", "es",
        r"\b(atentamente|su\s+(atento\s+y\s+)?seguro\s+servidor|s\.\s*s\.\s*s\.|afect[ií]simo|de\s+usted\s+atentamente)\b",
        2.0, where="tail", kind="Carta"),
    # --- Spanish: kinds only -----------------------------------------------------------------------
    Cue("ruling", "kind", "es", r"^\s*(FALLA|RESUELVE)\b", 0.0, where="any", kind="Sentencia", flags=re.MULTILINE),
    # --- English: openings -------------------------------------------------------------------------
    Cue("court-caption-en", "opening", "en", r"^\s*IN THE\b[^\n]{0,60}\bCOURT\b", 2.0, flags=re.MULTILINE),
    Cue("judgment-heading-en", "opening", "en", r"^\s*JUDG(E)?MENT\b", 2.5, kind="Judgment", flags=re.MULTILINE),
    Cue("letter-salutation-en", "opening", "en",
        r"^\s*((my\s+)?dear\b[^\n]{0,60}|sir|madam|gentlemen)[:,]\s*$", 2.5, kind="Letter"),
    Cue("cable-heading-en", "opening", "en", r"^\s*(TELEGRAM|CABLEGRAM)\b", 3.0, kind="Cable"),
    Cue("receipt-heading-en", "opening", "en", r"^\s*(RECEIPT|RECEIVED)\b", 2.5, kind="Receipt", flags=re.MULTILINE),
    Cue("place-and-date-en", "opening", "en",
        rf"^\s*({_PLACE})?((\d{{1,2}}(st|nd|rd|th)?\s+({_EN_MONTH}),?\s+\d{{4}})|(({_EN_MONTH})\s+\d{{1,2}}(st|nd|rd|th)?,?\s+\d{{4}}))\s*\.?\s*$",
        1.5),
    # --- English: closings -------------------------------------------------------------------------
    Cue("letter-closing-en", "closing", "en",
        r"\b(yours\s+(faithfully|truly|sincerely|respectfully)|sincerely(\s+yours)?|respectfully\s+yours)\b", 2.0,
        where="tail", kind="Letter"),
    Cue("typed-signature-en", "closing", "en", r"\(\s*(sgd|signed)\.?\s*\)", 1.0, where="tail"),
)

#: How many non-empty lines are a page's head and tail.
HEAD_LINES = 5
TAIL_LINES = 6
#: The most the opening (or closing) cues of one page may add together: two captions are not twice the evidence.
OPENING_CAP = 5.0
CLOSING_CAP = 3.0

# --- Page furniture: folio and page numbers ---------------------------------------------------------
#: A line that is only a page number ("- 3 -", "(12)", "3"), or names one ("Folio 3", "página 3 de 5").
FOLIO_PATTERNS = (
    re.compile(r"^\s*[-–—(\[]?\s*(\d{1,3})\s*[-–—)\]]?\s*$"),
    re.compile(r"^\s*(?:folio|fol\.|f\.|p[aá]gina|p[aá]g\.|page|p\.)\s*(\d{1,3})\b", re.IGNORECASE),
)
NUMBERING_RESTARTS = 2.0
NUMBERING_CONTINUES = -3.0

# --- Continuity across the break --------------------------------------------------------------------
#: Page n ends mid-sentence and page n+1 starts in lower case: the sentence runs over the break.
SENTENCE_RUNS_OVER = -3.0
#: Page n ends with a word broken by a hyphen.
WORD_SPLIT = -4.0
SENTENCE_END = re.compile(r"[.!?:;»\"”’)\]]\s*$")

# --- Who and what -----------------------------------------------------------------------------------
NAME = r"[A-ZÁÉÍÓÚÑ][\wáéíóúñ.'-]*(?:\s+(?:de\s+la\s+|de\s+los\s+|de\s+las\s+|del\s+|de\s+|y\s+|&\s+)?[A-ZÁÉÍÓÚÑ][\wáéíóúñ.'-]*){0,5}"
_TITLE = r"(?:(?i:señor(?:a)?|sr\.|sra\.|don|doña|dr\.|mr\.?|mrs\.?|miss|the)\s+)?"
#: Patterns whose one group is a party's name: "contra X", "demandante X", "X v. Y", a letter's addressee.
PARTY_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("against", re.compile(rf"(?i:\bcontra)\s+(?:(?i:el|la|los|las)\s+)?{_TITLE}({NAME})")),
    ("plaintiff", re.compile(rf"(?i:\bdemandante|\bactor|\bplaintiff|\bpromovid[oa]\s+por)[,:]?\s+{_TITLE}({NAME})")),
    ("defendant", re.compile(rf"(?i:\bdemandad[oa]|\bdefendant)[,:]?\s+{_TITLE}({NAME})")),
    ("versus", re.compile(rf"({NAME})\s+(?:v\.|vs\.?|versus)\s+")),
    ("addressee", re.compile(rf"^\s*(?i:dear|estimad[oa]|señor(?:a)?|sr\.|sra\.)\s+{_TITLE}({NAME})\s*[:,]\s*$",
                             re.MULTILINE)),
)
#: Words a name pattern may catch that are not names.
NOT_NAMES = frozenset({"el", "la", "los", "las", "de", "del", "juez", "juzgado", "señor", "señora", "sir", "madam",
                       "don", "doña", "mr", "mrs", "the", "trabajo", "circuito"})


def head(lines: list[str]) -> list[str]:
    return lines[:HEAD_LINES]


def tail(lines: list[str]) -> list[str]:
    return lines[-TAIL_LINES:]
