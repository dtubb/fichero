"""The synthetic evaluation set and the scorer with its pass bar (#6846).

spec: kg-paragraph-realisation (`kg.para.eval-set`, `kg.para.pass-bar`)

Three invented names (a person, a place, an organisation), each with the same 26 statements
shaped like the engine's rows, in Spanish, English, Portuguese (a language with no table)
and with no language. The scorer reads the answer of `GET /api/kg/entities/{id}/readable`
and returns, per measure of the spec's pass-bar table, the violations it found.

The scorer reads `clauses`, `segments`, `also_mentioned_in` and each clause's `date`,
`place` and `doubt`. The route does not return them yet, so
`test_the_route_answer_meets_the_pass_bar` is red until the steps that build them
(#6835 to #6845) have landed. No archive data: every name is invented.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

import pytest

from fichero_server.models.knowledge import (
    ClaimCurationState,
    ClaimRelationType,
    EpistemicStatus,
    EvidenceBasis,
    EvidentialDateRange,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
)

TABLE_LANGUAGES = ("es", "en")
HEDGES = (", al parecer,", ", apparently,", "una sola fuente", "one source only")
EXACT_FOR = {"day", "month", "year"}


@dataclass
class Row:
    """One invented statement and what the scorer expects of its clause."""

    key: str
    subject: str  # "P" the page name, or "A" / "B": another invented name
    verb: str
    obj: str  # "{P}", "{A}", "{B}", "{L1}", "{L2}" are replaced by the case's names
    lang: str | None = "es"
    time: tuple[str, str, str] | None = None  # time_start, time_end, time_precision
    dates: list[dict] = field(default_factory=list)  # EvidentialDateRange keywords
    place: str | None = None  # "L1" / "L2": the statement's own place (claim_location)
    docs: int = 1
    tentative: bool = False
    curated: bool = False
    confirmed_low: bool = False
    rejected: bool = False
    merged_into: str | None = None
    contradicts: str | None = None
    mention_only: bool = False
    # expectations
    date_said: dict[str, str] | None = None  # language -> the date as the clause says it
    level: str | None = None
    finer: tuple[str, ...] = ()  # strings that would say the date finer than held
    doubt: str | None = None
    mark_words: dict[str, str] | None = None  # language -> words an inferred or bound date takes


ROWS: list[Row] = [
    Row("born_a", "P", "nació en", "{L1}", time=("1702-03-14", "1702-03-14", "day"),
        contradicts="born_b", doubt="disputed", date_said={"es": "el 14 de marzo de 1702"},
        level="day"),
    Row("born_b", "P", "nació en", "{L1}", time=("1704-01-01", "1704-12-31", "year"),
        doubt="disputed", date_said={"es": "en 1704"}, level="year", finer=("1 de enero",)),
    Row("married", "P", "casó con", "{A}", time=("1722-09-30", "1722-09-30", "day"),
        place="L1", date_said={"es": "el 30 de septiembre de 1722"}, level="day"),
    Row("sold_house", "P", "vendió", "una casa de teja", time=("1731-06-01", "1731-06-30", "month"),
        place="L1", docs=2, date_said={"es": "en junio de 1731"}, level="month",
        finer=("1 de junio", "30 de junio")),
    Row("sold_house_dup", "P", "vendió", "una casa de teja", time=("1731-06-01", "1731-06-30", "month"),
        merged_into="sold_house", rejected=False),
    Row("sued", "B", "demandó a", "{P}", time=("1733-01-01", "1733-12-31", "year"),
        tentative=True, doubt="one_source_unsure", date_said={"es": "en 1733"}, level="year",
        finer=("1 de enero",)),
    Row("appeared", "B", "compareció ante", "{P}", time=("1734-01-01", "1734-12-31", "year"),
        date_said={"es": "en 1734"}, level="year", finer=("1 de enero",)),
    Row("bought", "P", "compró", "dos mulas", time=("1736-01-01", "1736-12-31", "year"),
        date_said={"es": "en 1736"}, level="year", finer=("1 de enero",)),
    Row("widowed", "P", "enviudó de", "{A}",
        dates=[dict(start="1738-01-01", circa=True, precision="year", basis=EvidenceBasis.inferred)],
        date_said={"es": "hacia 1738"}, level="about", mark_words={"es": "(fecha inferida)"}),
    Row("executor", "A", "nombró a", "{P} albacea", time=("1740-11-02", "1740-11-02", "day"),
        date_said={"es": "el 2 de noviembre de 1740"}, level="day"),
    Row("witness_will", "P", "fue testigo del testamento de", "{A}",
        time=("1741-01-01", "1741-12-31", "year"), place="L1",
        date_said={"es": "en 1741"}, level="year", finer=("1 de enero",)),
    Row("witness_sale", "P", "fue testigo de", "la venta de una estancia",
        time=("1743-05-09", "1743-05-09", "day"), place="L2",
        date_said={"es": "el 9 de mayo de 1743"}, level="day"),
    Row("arrived", "P", "arrived at", "{L2}", lang="en", time=("1744-08-01", "1744-08-31", "month"),
        date_said={"en": "in August 1744"}, level="month", finer=("1 August", "August 1,")),
    Row("witness_deed", "P", "fue testigo de", "un poder", time=("1745-01-01", "1745-12-31", "year"),
        date_said={"es": "en 1745"}, level="year", finer=("1 de enero",)),
    Row("served", "P", "served as", "administrator of the Arenal estate", lang="en",
        time=("1746-01-01", "1749-12-31", "range"),
        date_said={"en": "from 1746 to 1749"}, level="span"),
    Row("appointed", "A", "appointed", "{P}", lang="en", time=("1746-01-01", "1746-12-31", "year"),
        date_said={"en": "in 1746"}, level="year", finer=("1 January",)),
    Row("will", "P", "otorgó", "testamento",
        dates=[dict(start="1751-01-01", open_end=True, precision="year", basis=EvidenceBasis.asserted)],
        date_said={"es": "en 1751 o después"}, level="on_or_after",
        mark_words={"es": "o después"}),
    Row("power", "P", "otorgó", "un poder",
        dates=[dict(end="1760-12-31", open_start=True, precision="year", basis=EvidenceBasis.asserted)],
        date_said={"es": "en 1760 o antes"}, level="on_or_before",
        mark_words={"es": "o antes"}),
    Row("undated", "P", "era vecina de", "{L1}"),
    Row("died_rejected", "P", "murió en", "{L2}", time=("1750-01-01", "1750-12-31", "year"), rejected=True),
    Row("mention", "A", "pagó a", "{B}", mention_only=True),
    Row("inherited", "P", "heredó", "una estancia", time=("1752-01-01", "1752-12-31", "year"),
        confirmed_low=True, date_said={"es": "en 1752"}, level="year", finer=("1 de enero",)),
    Row("born_pt", "P", "nasceu em", "{L1}", lang="pt", time=("1710-01-01", "1710-12-31", "year")),
    Row("no_language", "P", "poseía", "unos libros", lang=None, time=("1755-01-01", "1755-12-31", "year")),
    Row("curated", "P", "compró", "una casa", curated=True, time=("1756-01-01", "1756-12-31", "year"),
        date_said={"es": "en 1756"}, level="year", finer=("1 de enero",)),
]

CASES = {
    "person": dict(P="Inés Valcárcel Montaño", A="Clemente Ibarra", B="Baltasar Oquendo",
                   L1="Villa Arenal", L2="San Telmo del Río"),
    "place": dict(P="Puerto Salinas", A="Rosendo Taborda", B="Casilda Neira",
                  L1="Cerro Alto", L2="Vega del Sauce"),
    "organisation": dict(P="Cofradía de la Santa Aurora", A="Leocadio Fresno", B="Amparo Villegas",
                         L1="Tierra Blanca", L2="Monte Claro"),
}


@dataclass
class Case:
    name: str
    entity_id: str
    names: dict[str, str]
    rows: dict[str, Row]
    claims: dict[str, KnowledgeClaim]  # by claim id
    ids: dict[str, str]  # row key -> claim id

    def selected(self) -> list[Row]:
        return [r for r in self.rows.values()
                if not (r.rejected or r.merged_into or r.mention_only)]

    def fill(self, text: str) -> str:
        return re.sub(r"\{(\w+)\}", lambda m: self.names[m.group(1)], text)


def build_case(db, name: str) -> Case:
    names = CASES[name]
    ents = {k: KnowledgeEntity(canonical_name=names[k]) for k in ("P", "A", "B")}
    for e in ents.values():
        db.save(e)
    ids = {r.key: f"{name}-{r.key}" for r in ROWS}
    case = Case(name, ents["P"].id, names, {r.key: r for r in ROWS}, {}, ids)
    for r in ROWS:
        subj = names[r.subject]
        obj = case.fill(r.obj)
        languages = [r.lang] if r.lang else []
        kw: dict = {}
        if r.time:
            kw.update(time_start=r.time[0], time_end=r.time[1], time_precision=r.time[2])
        if r.dates:
            kw["date_values"] = [EvidentialDateRange(**d) for d in r.dates]
        if r.place:
            kw["claim_location"] = names[r.place]
        if r.tentative:
            kw["epistemic_status"] = EpistemicStatus.tentative
        if r.curated:
            kw["curation_state"] = ClaimCurationState.curated
        if r.confirmed_low:
            kw.update(epistemic_status=EpistemicStatus.confirmed, confidence=0.1,
                      confidence_source="measured")
        if r.rejected:
            kw["curation_state"] = ClaimCurationState.rejected
        if r.merged_into:
            kw["merged_into_id"] = ids[r.merged_into]
        claim = KnowledgeClaim(
            id=ids[r.key], text=f"{subj} {r.verb} {obj}", svo_subject=subj, svo_verb=r.verb,
            svo_object=obj, subject_entity_id=ents[r.subject].id,
            entity_ids=sorted({ents["P"].id, ents[r.subject].id}),
            source_languages=languages, language=r.lang,
            source_document_id=f"{name}-doc-{r.key}-1",
            source_ids=[f"{name}-doc-{r.key}-{n}" for n in range(2, r.docs + 1)], **kw,
        )
        db.save(claim)
        case.claims[claim.id] = claim
    for r in ROWS:
        if r.contradicts:
            db.save(KnowledgeClaimLink(
                claim_id=ids[r.key], related_claim_id=ids[r.contradicts],
                relation_type=ClaimRelationType.contradicts))
    return case


def role_of(case: Case, row: Row) -> str:
    if row.subject == "P":
        return "subject"
    return "mention" if row.mention_only else "object"


# ---- the scorer ----------------------------------------------------------------------


def _clauses(answer: dict) -> list[dict]:
    return [c for s in answer["sentences"] for c in s.get("clauses", [])]


def _clause_for(answer: dict, claim_id: str) -> dict | None:
    return next((c for c in _clauses(answer) if claim_id in c["claim_ids"]), None)


def _text(answer: dict, span: dict) -> str:
    return answer["paragraph"][span["start"]:span["end"]]


def score(case: Case, answer: dict) -> dict[str, list[str]]:
    """Violations by measure of the pass bar; every list empty is a pass."""
    v: dict[str, list[str]] = {}
    ids = case.ids
    para = answer["paragraph"]
    said = {cid for s in answer["sentences"] for cid in s["claim_ids"]}
    listed = {m["claim_id"] for m in answer.get("also_mentioned_in", [])}

    v["rejected or merged statements said"] = [
        r.key for r in case.rows.values() if (r.rejected or r.merged_into) and ids[r.key] in said | listed]
    v["mention-only statements in the paragraph"] = [
        r.key for r in case.rows.values() if r.mention_only and ids[r.key] in said]

    v["selected statements in exactly one clause"] = [
        r.key for r in case.selected()
        if sum(ids[r.key] in c["claim_ids"] for c in _clauses(answer)) != 1]

    bad = []
    for s in answer["sentences"]:
        covered = set()
        for seg in s.get("segments", []):
            covered.update(range(seg["start"], seg["end"]))
        bad += [f"{i}:{para[i]}" for i in range(s["start"], s["end"])
                if para[i].isalnum() and i not in covered]
    v["letters and digits inside a segment with an origin"] = bad

    bad = []
    for s in answer["sentences"]:
        for seg in s.get("segments", []):
            kind, _, rest = seg["origin"].partition(":")
            if kind != "claim":
                continue
            cid, _, fld = rest.partition(":")
            value = str(getattr(case.claims[cid], fld, None) or "")
            text = _text(answer, seg)
            if text not in value and text[:1].lower() + text[1:] not in value:
                bad.append(f"{cid}:{fld}:{text}")
    v["claim segments that are substrings of their field"] = bad

    dated, finer, places, marks, hedged, subjects = [], [], [], [], [], []
    for r in case.selected():
        clause = _clause_for(answer, ids[r.key])
        lang = r.lang or ""
        if clause is None:
            for bucket, cond in ((dated, r.date_said), (places, r.place), (marks, r.doubt or r.mark_words)):
                if cond:
                    bucket.append(r.key)
            if r.confirmed_low or r.curated:
                hedged.append(r.key)
            subjects.append(r.key)
            continue
        ctext = _text(answer, clause)
        date = clause.get("date") or {}
        if r.date_said and (date.get("text") != r.date_said.get(lang) or date.get("level") != r.level):
            dated.append(r.key)
        finer += [f"{r.key}:{f}" for f in r.finer if f in ctext or f in (date.get("text") or "")]
        if r.place and (clause.get("place") or {}).get("text") != case.names[r.place] \
                and case.names[r.place] not in case.fill(r.obj):
            places.append(r.key)
        if r.doubt and clause.get("doubt") != r.doubt:
            marks.append(r.key)
        if r.mark_words and r.mark_words.get(lang) not in ctext + " " + para[clause["end"]:clause["end"] + 20]:
            marks.append(r.key)
        if (r.confirmed_low or r.curated) and (clause.get("doubt") != "none" or any(h in ctext for h in HEDGES)):
            hedged.append(r.key)
        if r.subject != "P" and not clause.get("revoiced") and case.names[r.subject] not in ctext:
            subjects.append(r.key)
    v["dated statements whose date is said at its level"] = dated
    v["dates said finer than held"] = finer
    v["places said, or already in the object"] = places
    v["statements needing a mark that carry it"] = marks
    v["statements a person confirmed that carry a hedge"] = hedged
    v["false subjects"] = subjects

    texts = [s["text"] for s in answer["sentences"]]
    v["identical sentences"] = sorted({t for t in texts if texts.count(t) > 1})

    allowed = 1 + sum(s["language"] not in TABLE_LANGUAGES for s in answer["sentences"])
    full = para.count(case.names["P"])
    v["full canonical name"] = [] if full <= allowed else [f"{full} times, at most {allowed}"]
    v["words in the longest sentence"] = [
        s["text"] for s in answer["sentences"] if len(s["text"].split()) > 40]
    return v


def failures(violations: dict[str, list[str]]) -> dict[str, list[str]]:
    return {k: x for k, x in violations.items() if x}


# ---- the set covers every case ---------------------------------------------------------


def test_the_evaluation_set_covers_every_case():
    assert len(CASES) >= 3 and len(ROWS) >= 20
    rows = list(ROWS)
    levels = {r.level for r in rows if r.level}
    assert levels >= {"day", "month", "year", "span", "about", "on_or_after", "on_or_before"}
    assert any(r.place for r in rows)
    assert any(c in r.obj for r in rows for c in ("{L1}", "{L2}"))
    assert sum("{P}" in r.obj for r in rows) >= 4
    assert any(r.docs >= 2 for r in rows)
    assert any(r.contradicts for r in rows)
    assert any(r.rejected for r in rows) and any(r.merged_into for r in rows)
    assert any(r.mention_only for r in rows)
    assert any(r.tentative for r in rows) and any(r.confirmed_low for r in rows)
    assert any(r.dates and r.dates[0]["basis"] == EvidenceBasis.inferred for r in rows)
    languages = {r.lang for r in rows}
    assert {"es", "en", "pt", None} <= languages
    assert len({c["P"] for c in CASES.values()}) == len(CASES)
    assert len({r.key for r in rows}) == len(rows)


# ---- the scorer itself, on answers written by hand --------------------------------------


def _tiny_answer(case: Case) -> dict:
    """A one-statement answer that meets every measure the scorer reads."""
    cid = case.ids["bought"]
    text = "En 1736 compró dos mulas."

    def seg(a, b, origin):
        return {"start": a, "end": b, "origin": origin, "claim_ids": [cid]}

    return {
        "paragraph": text,
        "sentences": [
            {"text": text, "start": 0, "end": len(text), "language": "es",
             "claim_ids": [cid], "role": "subject", "revoiced": False,
             "clauses": [{"start": 0, "end": len(text), "claim_ids": [cid],
                          "role": "subject", "revoiced": False, "doubt": "none",
                          "date": {"text": "en 1736", "level": "year"}, "place": None}],
             "segments": [seg(0, 2, "table:es:in"), seg(3, 7, "table:es:year"),
                          seg(8, 14, f"claim:{cid}:svo_verb"),
                          seg(15, 24, f"claim:{cid}:svo_object"), seg(24, 25, "punctuation")]},
        ],
        "also_mentioned_in": [],
    }


def _one_row_case(case: Case) -> Case:
    keep = {k: r for k, r in case.rows.items() if k in ("bought", "died_rejected", "mention")}
    return Case(case.name, case.entity_id, case.names, keep, case.claims, case.ids)


def test_the_scorer_reports_no_violation_for_an_answer_that_meets_the_bar(db):
    case = _one_row_case(build_case(db, "person"))
    answer = _tiny_answer(case)
    assert failures(score(case, answer)) == {}


@pytest.mark.parametrize("measure, damage", [
    ("rejected or merged statements said",
     lambda a, c: a["sentences"][0].update(claim_ids=[c.ids["died_rejected"]])),
    ("mention-only statements in the paragraph",
     lambda a, c: a["sentences"][0].update(claim_ids=[c.ids["mention"]])),
    ("selected statements in exactly one clause",
     lambda a, c: a["sentences"][0].update(clauses=[])),
    ("dated statements whose date is said at its level",
     lambda a, c: a["sentences"][0]["clauses"][0]["date"].update(level="day")),
    ("identical sentences", lambda a, c: a["sentences"].append(dict(a["sentences"][0]))),
    ("full canonical name", lambda a, c: a.update(paragraph=a["paragraph"] + (" " + c.names["P"]) * 2)),
    ("words in the longest sentence",
     lambda a, c: a["sentences"][0].update(text="palabra " * 41)),
    ("claim segments that are substrings of their field",
     lambda a, c: a["sentences"][0]["segments"][2].update(end=a["sentences"][0]["segments"][2]["end"] + 1)),
])
def test_the_scorer_names_each_measure_it_catches(db, measure, damage):
    case = _one_row_case(build_case(db, "person"))
    answer = _tiny_answer(case)
    damage(answer, case)
    assert measure in failures(score(case, answer))


# ---- the pass bar, through the real route ----------------------------------------------


def _route(client, case: Case) -> dict:
    r = client.get(f"/api/kg/entities/{case.entity_id}/readable")
    assert r.status_code == 200
    return r.json()


@pytest.mark.parametrize("name", list(CASES))
def test_the_route_answer_meets_the_pass_bar(client, db, name):
    case = build_case(db, name)
    assert failures(score(case, _route(client, case))) == {}


@pytest.mark.parametrize("name", list(CASES))
def test_shuffled_input_gives_the_same_bytes_five_times(client, db, monkeypatch, name):
    case = build_case(db, name)
    first = _route(client, case)["paragraph"]
    assert first
    originals = {n: getattr(db, n) for n in ("query", "query_json_list_intersects")}
    for seed in range(5):
        rng = random.Random(seed)

        def shuffled(fn):
            def run(*a, **k):
                rows = list(fn(*a, **k))
                rng.shuffle(rows)
                return rows
            return run

        for n, fn in originals.items():
            monkeypatch.setattr(db, n, shuffled(fn))
        assert _route(client, case)["paragraph"] == first
