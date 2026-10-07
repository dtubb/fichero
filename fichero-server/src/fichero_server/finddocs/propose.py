"""From a folder's pages to a proposal: leaves first, then boundaries, kinds and groups (`finddocs.*`, #5550).

Pure: pages in (their text, and the ink and look of their image when known), a `DocumentsProposal` out.
The steps, cheap to dear, as the spec lays them out:

1. **Leaves first** (`finddocs.leaves-first`): a near-blank page right after a written one is its verso (its
   reading is short and its image holds almost no ink); a written page whose text is nearly the same as one
   just before it is a second shot of that leaf. Both are findings, never documents; they travel with the
   leaf they belong to. A written page with no reading is reported too, and still takes its place.
2. **Boundaries** (`finddocs.boundaries.proposed-with-evidence`): for each join between neighbouring written
   pages, the log-odds that a document starts at the second, from the cue table (`cues.py`): opening cues at
   its head, closing cues at the foot of the page before, folio numbers restarting or running on, and a
   sentence running over the break. Each join keeps its signals.
3. **Kinds** (`finddocs.kinds.prototypes`): the document's opening cue names its prototype (VISTOS:
   Sentencia; a salutation: Carta); a ruling or a closing cue names it when the opening does not.
4. **Groups** (`finddocs.groups.and-order`): documents sharing two parties (names after "contra",
   "demandante", a letter's addressee and signer, and the knowledge graph's people where present) are one
   group, ordered by date.

`score` measures a proposal against a person's breakdown (`finddocs.scored`).
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from fichero_server.finddocs import cues as C
from fichero_server.models.found_documents import (
    DocumentsProposal,
    PageFinding,
    ProposedDocument,
    ProposedGroup,
    ProposedJoin,
    Signal,
)

#: The prior log-odds that a document starts at any one join: most joins in a box are inside a document.
PRIOR = -3.5
#: Above this probability a join is proposed as a boundary.
BOUNDARY_AT = 0.5
#: A page with fewer characters of reading than this, and (when the image is known) less ink, is blank.
BLANK_TEXT_CHARS = 20
BLANK_INK = 0.01
#: Two written pages this alike in their text (0 to 1) are two shots of one leaf.
DUPLICATE_TEXT = 0.9
#: How far back a second shot is looked for, in written pages.
DUPLICATE_WINDOW = 6
#: Texts shorter than this are too short to call two pages the same.
DUPLICATE_MIN_CHARS = 40
#: Image hashes this close (bits of 64) support a duplicate.
DUPLICATE_HASH_BITS = 6
#: Documents sharing at least this many parties are proposed as one group.
GROUP_SHARED_PARTIES = 2
_EXCERPT = 80


@dataclass
class PageInput:
    """One page as Find the Documents reads it."""

    id: str
    text: str = ""
    #: The share of the image's pixels that are ink (0 to 1), from its thumbnail; None when not measured.
    ink: float | None = None
    #: A 64-bit average hash of the thumbnail; None when not measured.
    image_hash: int | None = None
    #: Names the knowledge graph found on the page (people and organisations), where present.
    names: list[str] = field(default_factory=list)

    @property
    def lines(self) -> list[str]:
        return [line.strip() for line in (self.text or "").splitlines() if line.strip()]


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).lower()


def _norm_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _fold(text)).strip()


def _excerpt(line: str) -> str:
    return line if len(line) <= _EXCERPT else line[: _EXCERPT - 1] + "…"


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _is_blank(page: PageInput) -> bool:
    short = len((page.text or "").strip()) < BLANK_TEXT_CHARS
    return short and (page.ink is None or page.ink < BLANK_INK)


def _hamming(a: int | None, b: int | None) -> int | None:
    return None if a is None or b is None else bin(a ^ b).count("1")


# --- 1. Leaves --------------------------------------------------------------------------------------


@dataclass
class _Unit:
    """A written page that is not a second shot: what boundaries are proposed between."""

    page: PageInput
    position: int
    #: Every page that travels with it: itself, its verso, its second shots and their versos.
    page_ids: list[str] = field(default_factory=list)


def _leaves(pages: list[PageInput]) -> tuple[list[_Unit], list[PageFinding], int, list[str]]:
    """(units, findings, leaves, pages before the first written page)."""
    units: list[_Unit] = []
    findings: list[PageFinding] = []
    leading: list[str] = []
    leaves = 0
    previous_kind = None  # "written" | "duplicate" | "blank"
    previous_id: str | None = None
    for position, page in enumerate(pages):
        if _is_blank(page):
            if previous_kind in ("written", "duplicate"):
                findings.append(PageFinding(kind="blank-verso", page_id=page.id, of_page_id=previous_id,
                                            reason="a near-blank page right after a written one: its verso"))
            else:
                leaves += 1
                findings.append(PageFinding(kind="blank-page", page_id=page.id,
                                            reason="a blank page with no written page before it"))
            (units[-1].page_ids if units else leading).append(page.id)
            previous_kind, previous_id = "blank", page.id
            continue
        original = _duplicate_of(page, units)
        if original is not None:
            unit, similarity, bits = original
            reason = f"its text is {similarity:.0%} the same as the page shot just before"
            if bits is not None:
                reason += f"; their images differ by {bits} of 64 bits"
            findings.append(PageFinding(kind="duplicate-shot", page_id=page.id, of_page_id=unit.page.id,
                                        similarity=round(similarity, 3), reason=reason))
            units[-1].page_ids.append(page.id)
            previous_kind, previous_id = "duplicate", page.id
            continue
        leaves += 1
        if not (page.text or "").strip():
            findings.append(PageFinding(kind="no-reading", page_id=page.id,
                                        reason="a written page (its image holds ink) with no reading yet"))
        units.append(_Unit(page=page, position=position, page_ids=[page.id]))
        previous_kind, previous_id = "written", page.id
    return units, findings, leaves, leading


def _duplicate_of(page: PageInput, units: list[_Unit]) -> tuple[_Unit, float, int | None] | None:
    text = _norm_text(page.text)
    if len(text) < DUPLICATE_MIN_CHARS:
        return None
    best: tuple[_Unit, float, int | None] | None = None
    for unit in units[-DUPLICATE_WINDOW:]:
        other = _norm_text(unit.page.text)
        if len(other) < DUPLICATE_MIN_CHARS or abs(len(other) - len(text)) > 0.2 * max(len(other), len(text)):
            continue
        similarity = SequenceMatcher(None, text, other, autojunk=False).ratio()
        bits = _hamming(page.image_hash, unit.page.image_hash)
        if similarity >= DUPLICATE_TEXT and (bits is None or bits <= DUPLICATE_HASH_BITS * 4):
            if best is None or similarity > best[1]:
                best = (unit, similarity, bits)
    return best


# --- 2. Boundaries ----------------------------------------------------------------------------------


def _cue_signals(page: PageInput, role: str) -> list[Signal]:
    lines = page.lines
    out: list[Signal] = []
    for cue in C.CUES:
        if cue.role != role:
            continue
        where = C.head(lines) if cue.where == "head" else C.tail(lines) if cue.where == "tail" else lines
        hit = next((line for line in where if cue.regex.search(line)), None)
        if hit is not None:
            out.append(Signal(cue=cue.id, role=role, weight=cue.weight, page_id=page.id, line=_excerpt(hit)))
    return out


def _folio(page: PageInput) -> int | None:
    lines = page.lines
    for line in [*C.head(lines)[:2], *C.tail(lines)[-2:]]:
        for pattern in C.FOLIO_PATTERNS:
            match = pattern.match(line)
            if match:
                return int(match.group(1))
    return None


def _join(previous: PageInput, page: PageInput) -> ProposedJoin:
    signals = _cue_signals(page, "opening")
    opening = min(C.OPENING_CAP, sum(s.weight for s in signals))
    closing_signals = _cue_signals(previous, "closing")
    closing = min(C.CLOSING_CAP, sum(s.weight for s in closing_signals))
    signals += closing_signals
    furniture = 0.0
    folio, folio_before = _folio(page), _folio(previous)
    if folio == 1:
        furniture = C.NUMBERING_RESTARTS
        signals.append(Signal(cue="numbering-restarts", role="furniture", weight=furniture, page_id=page.id))
    elif folio is not None and folio_before is not None and folio == folio_before + 1:
        furniture = C.NUMBERING_CONTINUES
        signals.append(Signal(cue="numbering-continues", role="furniture", weight=furniture, page_id=page.id))
    continuity = 0.0
    before_lines, after_lines = previous.lines, page.lines
    if before_lines and after_lines:
        last, first = before_lines[-1], after_lines[0]
        first_letter = next((c for c in first if c.isalpha()), "")
        if last.endswith("-") and not last.endswith("--"):
            continuity = C.WORD_SPLIT
            signals.append(Signal(cue="word-split", role="continuity", weight=continuity, page_id=page.id,
                                  line=_excerpt(last)))
        elif not C.SENTENCE_END.search(last) and first_letter.islower():
            continuity = C.SENTENCE_RUNS_OVER
            signals.append(Signal(cue="sentence-runs-over", role="continuity", weight=continuity, page_id=page.id,
                                  line=_excerpt(f"{last} / {first}")))
    probability = _sigmoid(PRIOR + opening + closing + furniture + continuity)
    return ProposedJoin(page_id=page.id, previous_page_id=previous.id, probability=round(probability, 4),
                        signals=signals)


# --- 3. Kinds, dates, parties -----------------------------------------------------------------------


def _kind(units: list[_Unit]) -> tuple[str | None, str | None]:
    """(kind, the cue that named it): the strongest opening cue with a kind on the first page, else a closing or
    a kind-only cue anywhere in the document."""
    first = units[0].page
    opening = _cue_signals(first, "opening")
    by_id = {cue.id: cue for cue in C.CUES}
    named = sorted((s for s in opening if by_id[s.cue].kind), key=lambda s: -s.weight)
    if named:
        return by_id[named[0].cue].kind, named[0].cue
    for unit in units:
        for signal in [*_kind_signals(unit.page), *_cue_signals(unit.page, "closing")]:
            if by_id[signal.cue].kind:
                return by_id[signal.cue].kind, signal.cue
    return None, None


def _kind_signals(page: PageInput) -> list[Signal]:
    lines = page.lines
    return [Signal(cue=cue.id, role="kind", weight=0.0, page_id=page.id, line=_excerpt(hit))
            for cue in C.CUES if cue.role == "kind"
            for hit in [next((line for line in lines if cue.regex.search(line)), None)] if hit is not None]


def prototype_key(kind: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _fold(kind)).strip("_")


_DATE_ES = re.compile(rf"\b(\d{{1,2}})\s+de\s+({'|'.join(C.MONTHS['es'])}|setiembre)\s+de\s+(\d{{4}})", re.IGNORECASE)
_DATE_EN_DMY = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({'|'.join(C.MONTHS['en'])}),?\s+(\d{{4}})", re.IGNORECASE)
_DATE_EN_MDY = re.compile(rf"\b({'|'.join(C.MONTHS['en'])})\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})", re.IGNORECASE)


def _date(text: str) -> str | None:
    found: list[tuple[int, str]] = []
    for pattern, order in ((_DATE_ES, "dmy"), (_DATE_EN_DMY, "dmy"), (_DATE_EN_MDY, "mdy")):
        for match in pattern.finditer(text):
            a, b, year = match.groups()
            day, month = (a, b) if order == "dmy" else (b, a)
            month = _fold(month)
            month = "septiembre" if month == "setiembre" else month
            number = (C.MONTHS["es"].index(month) if month in C.MONTHS["es"] else C.MONTHS["en"].index(month)) + 1
            if 1 <= int(day) <= 31:
                found.append((match.start(), f"{int(year):04d}-{number:02d}-{int(day):02d}"))
    return min(found)[1] if found else None


def _clean_name(name: str) -> str | None:
    words = [w for w in re.split(r"\s+", name.strip(" .,;:")) if w]
    while words and _fold(words[-1]).strip(".") in C.NOT_NAMES | {"y", "de", "del"}:
        words.pop()
    while words and _fold(words[0]).strip(".") in C.NOT_NAMES:
        words.pop(0)
    return " ".join(words) if words else None


def _parties(units: list[_Unit]) -> list[str]:
    names: list[str] = []
    for unit in units:
        text = "\n".join(unit.page.lines)
        for _role, pattern in C.PARTY_PATTERNS:
            for match in pattern.finditer(text):
                cleaned = _clean_name(match.group(1))
                if cleaned:
                    names.append(cleaned)
        names += _signers(unit.page)
        names += list(unit.page.names)
    return list(dict.fromkeys(names))


def _signers(page: PageInput) -> list[str]:
    """The name on the line after a letter's closing (its signer)."""
    lines = C.tail(page.lines)
    closings = [cue for cue in C.CUES if cue.role == "closing" and cue.kind in ("Carta", "Letter")]
    out = []
    for i, line in enumerate(lines[:-1]):
        if any(cue.regex.search(line) for cue in closings):
            match = re.fullmatch(C.NAME, lines[i + 1].strip(" .,"))
            if match and (cleaned := _clean_name(match.group(0))):
                out.append(cleaned)
    return out


def _same_party(a: str, b: str) -> bool:
    """The same person or body: equal, or one name is the other's last words ("Brown", "Robert Brown")."""
    x, y = _norm_text(a).split(), _norm_text(b).split()
    if not x or not y:
        return False
    short, long_ = (x, y) if len(x) <= len(y) else (y, x)
    return long_[-len(short):] == short


# --- 4. The proposal --------------------------------------------------------------------------------


def propose(pages: list[PageInput], *, proposal_id: str = "", folder_id: str | None = None,
            job_id: str | None = None) -> DocumentsProposal:
    """Find the documents in `pages` (in the folder's order)."""
    units, findings, leaves, leading = _leaves(pages)
    joins = [_join(units[i - 1].page, units[i].page) for i in range(1, len(units))]
    starts = [0] + [i for i, join in enumerate(joins, start=1) if join.probability >= BOUNDARY_AT]
    documents: list[ProposedDocument] = []
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(units)
        members = units[start:end]
        page_ids = (leading if n == 0 else []) + [pid for unit in members for pid in unit.page_ids]
        start_join = joins[start - 1] if start > 0 else None
        end_join = joins[end - 1] if end < len(units) else None
        inner = [joins[i - 1] for i in range(start + 1, end)]
        certainties = [start_join.probability if start_join else 1.0,
                       *(1.0 - j.probability for j in inner),
                       end_join.probability if end_join else 1.0]
        kind, kind_cue = _kind(members)
        date = _date("\n".join(members[0].page.lines))
        parties = _parties(members)
        reasons = []
        if start_join is not None:
            said = ", ".join(s.cue for s in start_join.signals if s.weight > 0) or "no cue"
            reasons.append(f"starts at page {members[0].position + 1}: {said} ({start_join.probability:.0%})")
        else:
            reasons.append(f"starts at page {members[0].position + 1}: the first written page")
        if kind:
            reasons.append(f"a {kind}: {kind_cue}")
        weakest = min(range(len(certainties)), key=certainties.__getitem__)
        if certainties[weakest] < 0.95:
            where = ("its start" if weakest == 0 else "its end" if weakest == len(certainties) - 1
                     else f"the join before page {members[weakest].position + 1}")
            reasons.append(f"least sure of {where} ({certainties[weakest]:.0%})")
        positions = [p for p, page in enumerate(pages) if page.id in set(page_ids)]
        documents.append(ProposedDocument(
            index=n, name=" ".join(x for x in (kind or "Document", date or "") if x).strip() or f"Document {n + 1}",
            page_ids=page_ids, first_position=min(positions), last_position=max(positions), kind=kind,
            prototype_key=prototype_key(kind) if kind else None, date=date, parties=parties,
            confidence=round(min(certainties), 4), reasons=reasons))
    return DocumentsProposal(id=proposal_id, folder_id=folder_id, page_ids=[p.id for p in pages], job_id=job_id,
                             leaves=leaves, documents=documents, groups=_groups(documents), findings=findings,
                             joins=joins)


def _groups(documents: list[ProposedDocument]) -> list[ProposedGroup]:
    """Documents sharing `GROUP_SHARED_PARTIES` parties, joined transitively, each group ordered by date."""
    parent = list(range(len(documents)))
    shared_by: dict[tuple[int, int], list[str]] = {}

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(documents):
        for j in range(i + 1, len(documents)):
            b = documents[j]
            shared = [x for x in a.parties if any(_same_party(x, y) for y in b.parties)]
            if len(shared) >= GROUP_SHARED_PARTIES:
                shared_by[(i, j)] = shared
                parent[find(j)] = find(i)
    clusters: dict[int, list[int]] = {}
    for i in range(len(documents)):
        clusters.setdefault(find(i), []).append(i)
    groups = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda i: (documents[i].date or "9999", documents[i].first_position))
        names = list(dict.fromkeys(x for (i, j), shared in shared_by.items() if i in members for x in shared))
        reasons = [f"documents {i + 1} and {j + 1} share {', '.join(shared)}"
                   for (i, j), shared in shared_by.items() if i in members]
        reasons.append("in order of their dates" if all(documents[i].date for i in members)
                       else "in order of their dates, then of the pages")
        groups.append(ProposedGroup(index=len(groups), label=" — ".join(names[:2]), document_indexes=ordered,
                                    parties=names, reasons=reasons))
    return groups


# --- Scoring against a person's breakdown -----------------------------------------------------------


def score(proposal: DocumentsProposal, truth: list[list[str]]) -> dict[str, float | int]:
    """Boundary precision and recall and exact documents (`finddocs.scored`), against a person's breakdown:
    `truth` is each document's pages in order. A boundary is the first page of a document; the first page of
    the box is not counted (it is always one)."""
    proposed = {d.page_ids[0] for d in proposal.documents[1:]}
    actual = {doc[0] for doc in truth[1:]}
    hits = len(proposed & actual)
    exact = sum(1 for d in proposal.documents if d.page_ids in truth)
    return {
        "precision": hits / len(proposed) if proposed else 1.0,
        "recall": hits / len(actual) if actual else 1.0,
        "exact_documents": exact,
        "documents": len(truth),
    }
