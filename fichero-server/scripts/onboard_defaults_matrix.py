#!/usr/bin/env python3
"""Set Up's defaults across languages and scripts, against the Test Corpus (#5969, #5970; spec `source.onboard.defaults.matrix-measured`,
`source.onboard.model-search-recorded`; brief `briefs/onboarding-defaults-matrix-2026-10-20.md`).

For each set of the Test Corpus (a folder of page images with a same-stem PAGE or ALTO file):
  1. TRUTH: what the set is, from `TRUTH` below (the corpus README's row: language, script, direction, material, classes) and from
     the language tags inside its PAGE/ALTO files.
  2. PROPOSED: what Set Up proposes for that truth, from the engine's own rules (the function behind `POST /api/recipes/assemble`,
     called in this process: no server, no network): the line finder, the reader with its reason, where it runs, the gap or the
     refusal in words, the cloud offer, and the direction a script derives.
  3. SCORED (where PAGE/ALTO text exists): 3 to 5 pages read by the free arms, CER and WER against the file's text:
     `seed` = the multilingual Kraken reader of the seed models (when its card lists the set's scripts), `vision` = Apple Vision on
     Kraken's lines; the proposed reader is scored when it is the seed reader, else it says "proposed X, not installed: not scored".
  4. With --search: Set Up's MODEL SEARCH for the set's language (public queries to Hugging Face and Zenodo, no page leaves), what
     it found for the script, and, when it found nothing, that said in words.

  python fichero-server/scripts/onboard_defaults_matrix.py --corpus DIR --out DIR [--pages 3] [--arms seed,vision] [--search]
         [--only "Syriac,Hindi"] [--seed-reader kraken-zenodo-21788410]

It runs in the engine's venv on the test Mac (the M4), ON AC, one heavy job at a time. READ-ONLY on the corpus (it opens images and
XML and writes nothing there); FICHERO_BASE_PATH must be a scratch directory holding a COPY of the dev seed models (the guard of
`ab_kraken_cloud.require_scratch_state`); nothing is imported into any project or library; no key or link is read or printed.

Writes to --out: matrix.md (the table), matrix.json (every row, every page), sets/<folder>.json. CER is the edit distance over the
text with whitespace collapsed (one string a page: the lines in the order Kraken gives them), so a set whose reading order differs
from the file's (vertical columns, two hands) scores worse than its lines deserve: the table says which sets those are."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

IMAGES = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}

# folder-name prefix -> (languages, scripts, direction, material, classes). Read off the corpus README's rows (language, script,
# direction) and the set names; an entry is a CLAIM about the set that the XML's own language tags then check. Codes are
# BCP 47 / ISO 15924. `classes`: rtl vertical non-latin table marginalia interlinear mixed print hand layout-only.
TRUTH: dict[str, dict[str, Any]] = {
    "Syriac - Vienna": dict(languages=["syr"], scripts=["Syrc"], direction="rtl", material="handwriting", classes=["rtl", "non-latin"]),
    "Syriac - Jerusalem MS 36, Transkribus": dict(languages=["syr"], scripts=["Syrc"], direction="rtl", material="handwriting", classes=["rtl", "non-latin"]),
    "Syriac - Jerusalem MS 36, eScriptorium": dict(languages=["syr"], scripts=["Syrc"], direction="rtl", material="handwriting", classes=["rtl", "non-latin"]),
    "Hebrew - BiblIA": dict(languages=["he"], scripts=["Hebr"], direction="rtl", material="handwriting", classes=["rtl", "non-latin"]),
    "Persian - nastaliq": dict(languages=["fa", "en"], scripts=["Arab", "Latn"], direction="rtl", material="handwriting", classes=["rtl", "non-latin", "mixed"]),
    "Ottoman Turkish": dict(languages=["ota"], scripts=["Arab"], direction="rtl", material="handwriting", classes=["rtl", "non-latin"]),
    "Urdu": dict(languages=["ur"], scripts=["Arab"], direction="rtl", material="handwriting", classes=["rtl", "non-latin"]),
    "Arabic with interlinear Persian": dict(languages=["ar", "fa"], scripts=["Arab"], direction="rtl", material="handwriting", classes=["rtl", "non-latin", "interlinear"]),
    "Malay in Jawi": dict(languages=["ms"], scripts=["Arab"], direction="rtl", material="handwriting", classes=["rtl", "non-latin"]),
    "Aljamiado": dict(languages=["es"], scripts=["Arab"], direction="rtl", material="handwriting", classes=["rtl", "non-latin"]),
    "Greek - polytonic": dict(languages=["grc"], scripts=["Grek"], direction="ltr", material="handwriting", classes=["non-latin"]),
    "Newa": dict(languages=["new", "sa"], scripts=["Newa"], direction="ltr", material="handwriting", classes=["non-latin"]),
    "Hindi": dict(languages=["hi"], scripts=["Deva"], direction="ltr", material="print", classes=["non-latin", "print"]),
    "Malayalam": dict(languages=["ml"], scripts=["Mlym"], direction="ltr", material="handwriting", classes=["non-latin"]),
    "Medieval Latin (MUFI)": dict(languages=["la"], scripts=["Latn"], direction="ltr", material="handwriting", classes=["hand"]),
    "Old French - BnF fr. 412": dict(languages=["fro"], scripts=["Latn"], direction="ltr", material="handwriting", classes=["hand"]),
    "Old Occitan": dict(languages=["pro"], scripts=["Latn"], direction="ltr", material="handwriting", classes=["hand"]),
    "Medieval Spanish": dict(languages=["es"], scripts=["Latn"], direction="ltr", material="handwriting", classes=["hand"]),
    "Latin and French - Notre-Dame": dict(languages=["la", "fr"], scripts=["Latn"], direction="ltr", material="handwriting", classes=["marginalia", "mixed"]),
    "Chinese - classical": dict(languages=["lzh"], scripts=["Hant"], direction="ttb", material="print", classes=["vertical", "non-latin"]),
    "Arabic - Maghrebi": dict(languages=["ar"], scripts=["Arab"], direction="rtl", material="handwriting", classes=["rtl", "non-latin"]),
    "Nahuatl": dict(languages=["nah"], scripts=["Latn"], direction="ltr", material="print", classes=["layout-only", "print"]),
    "Spanish - early modern notarial": dict(languages=["es"], scripts=["Latn"], direction="ltr", material="handwriting", classes=["hand"]),
    "English - Tesseract hOCR": dict(languages=["en"], scripts=["Latn"], direction="ltr", material="print", classes=["print"]),
    "Cree - handwritten": dict(languages=["cr"], scripts=["Cans"], direction="ltr", material="handwriting", classes=["non-latin"]),
    "Tibetan": dict(languages=["bo"], scripts=["Tibt"], direction="ltr", material="handwriting", classes=["non-latin", "layout-only"]),
    "Greek papyri": dict(languages=["grc"], scripts=["Grek"], direction="ltr", material="handwriting", classes=["non-latin"]),
    "Cherokee and English": dict(languages=["chr", "en"], scripts=["Cher", "Latn"], direction="ltr", material="print", classes=["non-latin", "mixed", "print"]),
    "Fulfulde in Arabic script": dict(languages=["ff"], scripts=["Arab"], direction="rtl", material="handwriting", classes=["rtl", "non-latin"]),
    "Classical Armenian": dict(languages=["xcl"], scripts=["Armn"], direction="ltr", material="handwriting", classes=["non-latin"]),
    "Japanese - Tale of Genji": dict(languages=["ja"], scripts=["Jpan"], direction="ttb", material="print", classes=["vertical", "non-latin", "print"]),
    "YOLO layout - YALTAi SegmOnto": dict(languages=["la", "fr"], scripts=["Latn"], direction="ltr", material="handwriting", classes=["layout-only"]),
    "YOLO layout - YALTAi tables": dict(languages=["fr"], scripts=["Latn"], direction="ltr", material="handwriting", classes=["table", "layout-only"]),
    "Medieval vernacular religious": dict(languages=["ga", "sv", "es", "de", "fr"], scripts=["Latn"], direction="ltr", material="handwriting", classes=["hand", "mixed"]),
    "French - 15th-century illuminated": dict(languages=["fr"], scripts=["Latn"], direction="ltr", material="handwriting", classes=["hand"]),
    "Latin with interlinear glosses": dict(languages=["la"], scripts=["Latn"], direction="ltr", material="handwriting", classes=["interlinear"]),
    "Latin canon law": dict(languages=["la"], scripts=["Latn"], direction="ltr", material="handwriting", classes=["layout-only"]),
    "Czech": dict(languages=["cs"], scripts=["Latn"], direction="ltr", material="handwriting", classes=["hand"]),
    "German - Neue Zürcher Zeitung": dict(languages=["de"], scripts=["Latn"], direction="ltr", material="print", classes=["print"]),
    "French - Paris notaries": dict(languages=["fr"], scripts=["Latn"], direction="ltr", material="handwriting", classes=["table", "hand", "print", "mixed"]),
    "German - Reichsanzeiger": dict(languages=["de"], scripts=["Latn"], direction="ltr", material="print", classes=["table", "print"]),
    "English - USS Albatross": dict(languages=["en"], scripts=["Latn"], direction="ltr", material="handwriting", classes=["table", "hand", "print", "mixed"]),
    "Colombia": dict(languages=["es"], scripts=["Latn"], direction="ltr", material="handwriting", classes=["hand"]),
    "Latin and Old English": dict(languages=["la", "ang"], scripts=["Latn"], direction="ltr", material="handwriting", classes=["mixed"]),
    "Repository test fixtures": dict(languages=["es"], scripts=["Latn"], direction="ltr", material="handwriting", classes=["hand"]),
}


def truth_for(folder: str) -> dict[str, Any] | None:
    """The TRUTH row whose key is the longest prefix of the folder's name, or None (a set the table does not know is reported, not guessed)."""
    hits = [key for key in TRUTH if folder.startswith(key)]
    return TRUTH[max(hits, key=len)] if hits else None


def _text(node: ET.Element) -> str:
    return "".join(node.itertext())


def page_truth(xml_path: Path) -> dict[str, Any]:
    """{'text': the page's lines joined by a space (whitespace collapsed), 'lines': n, 'languages': [tags the file carries]} from a
    PAGE or ALTO file; text '' when it carries no line text. Namespace-blind, so any PAGE or ALTO version reads."""
    try:
        root = ET.parse(xml_path).getroot()
    except (ET.ParseError, OSError):
        return {"text": "", "lines": 0, "languages": []}
    lines: list[str] = []
    languages: set[str] = set()
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        for attr in ("primaryLanguage", "language", "LANG", "lang"):
            value = el.get(attr)
            if value:
                languages.add(value.strip())
        if tag == "TextLine":
            unicode_ = [u for u in el.iter() if u.tag.rsplit("}", 1)[-1] == "Unicode"]
            last = (unicode_[-1].text or "").strip() if unicode_ else ""
            if last:  # PAGE: the line's own TextEquiv comes last (its words come before it)
                lines.append(last)
                continue
            words = [s.get("CONTENT", "") for s in el.iter() if s.tag.rsplit("}", 1)[-1] == "String"]  # ALTO
            if any(words):
                lines.append(" ".join(w for w in words if w))
    return {"text": re.sub(r"\s+", " ", " ".join(lines)).strip(), "lines": len(lines), "languages": sorted(languages)}


def error_rates(truth: str, read: str) -> dict[str, float | None]:
    """CER and WER of `read` against `truth` (whitespace collapsed); None when the truth is empty."""
    from fichero_server.llm.multilingual import levenshtein_distance

    t, r = re.sub(r"\s+", " ", truth).strip(), re.sub(r"\s+", " ", read).strip()
    if not t:
        return {"cer": None, "wer": None}
    tw, rw = t.split(" "), r.split(" ")
    words = {w: chr(0x4E00 + i) for i, w in enumerate(dict.fromkeys(tw + rw))}  # one private character per word: edit distance over words
    return {"cer": levenshtein_distance(t, r) / len(t),
            "wer": levenshtein_distance("".join(words[w] for w in tw), "".join(words[w] for w in rw)) / len(tw)}


def sets_in(corpus: Path, only: list[str]) -> list[Path]:
    folders = sorted(p for p in corpus.iterdir() if p.is_dir())
    return [p for p in folders if not only or any(o.lower() in p.name.lower() for o in only)]


def pages_of(folder: Path, count: int) -> list[tuple[Path, Path | None]]:
    """(image, its same-stem PAGE/ALTO file or None) for the first `count` images in name order that have one; if none has,
    the first images with None (the read is timed but not scored)."""
    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGES)
    paired = [(p, p.with_suffix(".xml")) for p in images if p.with_suffix(".xml").exists()]
    return (paired or [(p, None) for p in images])[:count]


def proposal(truth: dict[str, Any]) -> dict[str, Any]:
    """What Set Up proposes for this truth: the engine's own assemble (the function behind POST /api/recipes/assemble)."""
    from fichero_server.api.routes.system.recipes import _assemble
    from fichero_server.recipes.answers import default_direction

    answers = {"purposes": ["transcribe"], "languages": truth["languages"], "scripts": truth["scripts"],
               "materials": [truth["material"]], "pages": 100}
    try:
        recipe = _assemble(answers)
    except ValueError as exc:  # a language or script the registry refuses, said in words
        return {"refused": str(exc), "steps": {}, "direction": None}
    steps = {}
    for step in recipe["steps"]:
        if step["job"] in ("find-regions", "find-lines", "read-a-line", "read-a-page"):
            card = step.get("card") or {}
            problem = step.get("problem") or {}
            steps[step["job"]] = {"card": card.get("id"), "name": card.get("note", "")[:80], "runs_on": step.get("runs_on"),
                                  "cer_published": card.get("cer_published"), "reason": (step.get("reasons") or [""])[0],
                                  "gap": step.get("gap"), "problem": problem.get("kind") if isinstance(problem, dict) else None}
    return {"steps": steps, "gaps": recipe.get("gaps", []), "cloud_options": recipe.get("cloud_options", []),
            "direction": {s: default_direction(s) for s in truth["scripts"]}}


def step_of(prop: dict[str, Any], job: str) -> dict[str, Any]:
    """The proposal's step for `job`, whether `steps` is this script's dict by job or a recipe's own list; {} when there is none."""
    steps = prop.get("steps") or {}
    if isinstance(steps, list):
        return next((s for s in steps if isinstance(s, dict) and s.get("job") == job), {})
    return steps.get(job) or {}


def judge(truth: dict[str, Any], prop: dict[str, Any]) -> str:
    """right? in one word: WRONG-direction, none-says-so (no reader and it says so), refused, ok (a reader whose card lists the
    scripts and the direction is the script's), or check (a person looks)."""
    if prop.get("refused"):
        return "refused"
    wanted = truth["direction"]
    derived = set((prop.get("direction") or {}).values())
    if derived and wanted not in derived and not (wanted == "ltr" and derived <= {"ltr"}):
        return "WRONG-direction"
    reader = step_of(prop, "read-a-line") or step_of(prop, "read-a-page")
    if reader.get("card"):
        return "ok" if "layout-only" not in truth["classes"] else "check"
    return "none-says-so" if (reader.get("gap") or reader.get("problem")) else "check"


#: Set (once) by the first AppleVisionStuck of this process (the engine's gate refuses at once past its ceiling of abandoned calls,
#: #5392); the vision arm reads nothing after it. A single timeout does not set it: the engine frees that call's slot.
_VISION_STUCK: list[str] = []
#: Each Apple Vision call here is one small line picture: a minute is long. The engine's default is 300 s a call, and a stuck call
#: costs that for every line behind it (the 06:20 to 06:31 stall of the 2026-10-21 run).
VISION_TIMEOUT_SECONDS = "60"


def read_pages(arm: str, pages: list[tuple[Path, Path | None]], seed_reader: str) -> list[dict[str, Any]]:
    """Read each page with an arm and score it against its file's text. One row per page: seconds, lines, cer, wer, or an error in words."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ab_kraken_cloud as ab

    rows = []
    for image, xml in pages:
        if arm == "vision" and _VISION_STUCK:
            rows.append({"page": image.name, "error": f"AppleVisionStuck: not tried: {_VISION_STUCK[0]}"})
            continue
        truth = page_truth(xml) if xml else {"text": "", "lines": 0, "languages": []}
        began = time.perf_counter()
        try:
            lines = ab.kraken_lines(image, seed_reader)
            if arm == "seed":
                read = " ".join(ln["text"] for ln in lines)
            else:
                import asyncio

                got = asyncio.run(ab.free_reader("vision", fake=False)(image, lines))
                read = " ".join(got.get(ln["id"], "") for ln in lines)
            rows.append({"page": image.name, "seconds": round(time.perf_counter() - began, 1), "lines": len(lines),
                         **error_rates(truth["text"], read), "truth_lines": truth["lines"]})
        except Exception as exc:  # noqa: BLE001 -- a page that fails is a result, in words
            rows.append({"page": image.name, "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
            if type(exc).__name__ == "AppleVisionStuck" and not _VISION_STUCK:
                # The call that timed out is abandoned, not ended: it keeps its slot of the engine's Apple Vision gate (#5392), so
                # every later call would wait out its own deadline for nothing. Stop asking, say so, and go on with the other arm.
                _VISION_STUCK.append("Apple Vision is stuck (several calls never returned, #5392); the vision arm is "
                                     "skipped for the rest of this run. Run it again in a fresh process")
                print(f"! vision arm stopped: {_VISION_STUCK[0]}", flush=True)
    return rows


def mean(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [r[key] for r in rows if isinstance(r.get(key), float)]
    return round(sum(values) / len(values), 3) if values else None


def search_for(truth: dict[str, Any]) -> dict[str, Any]:
    """Set Up's model search for this truth (public queries), then what the plan would consider: the cards that read this script."""
    from fichero_server.recipes import discovery
    from fichero_server.recipes.assemble import Answers, _refusal
    from fichero_server.recipes.names import resolve_language, resolve_script

    languages = frozenset(resolve_language(code) for code in truth["languages"])
    try:
        said = discovery.search_online(languages)
    except Exception as exc:  # noqa: BLE001 -- offline, refused, unreachable: said in words
        return {"searched": False, "why": str(exc)[:200]}
    a = Answers(purposes=("transcribe",), languages=languages, scripts=frozenset(resolve_script(s) for s in truth["scripts"]),
                materials=(truth["material"],))
    found = []
    for card in discovery.known_cards(a):
        for job in ("read-a-line", "read-a-page"):
            if job in card.jobs and _refusal(job, card, a, truth["material"]) is None:
                found.append({"id": card.id, "runs_on": card.runs_on, "licence": card.licence, "cer_published": card.cer_published})
                break
    sources = {name: src.get("detail") or src.get("state") for name, src in said["sources"].items()}
    gap = None if found else ("Set Up's search found no model that reads this script and language. A person can train one from "
                              "about a hundred corrected lines, or use a cloud reader if the project lets pages leave.")
    return {"searched": True, "sources": sources, "found": found[:8], "n_found": len(found), "nothing_found": gap}


def report(rows: list[dict[str, Any]]) -> str:
    head = ("| set | truth (lang / script / dir / classes) | proposed reader (runs on) | right? | CER default | CER seed | CER vision "
            "| better option | search found | issue |\n|---|---|---|---|---|---|---|---|---|---|\n")
    out = []
    for r in rows:
        t, p = r["truth"], r["proposed"]
        reader = step_of(p, "read-a-line") or step_of(p, "read-a-page")
        proposed = (f"{reader.get('card')} ({reader.get('runs_on')})" if reader.get("card")
                    else (p.get("refused") or reader.get("gap") or reader.get("problem") or "nothing"))
        best = None
        scored = {a: r["scores"][a]["cer"] for a in r["scores"] if r["scores"][a].get("cer") is not None}
        base = r["scores"].get("default", {}).get("cer", r["scores"].get("seed", {}).get("cer"))
        if scored and base is not None:
            arm, cer = min(scored.items(), key=lambda kv: kv[1])
            best = f"{arm} ({cer:.2f} vs {base:.2f})" if cer < base - 0.01 else "-"
        found = r.get("search")
        found_text = "not run" if not found else (found.get("nothing_found") or f"{found['n_found']}: " + ", ".join(
            f["id"] for f in found["found"][:3])) if found.get("searched") else f"not searched: {found.get('why')}"

        def fmt(arm):
            value = r["scores"].get(arm, {}).get("cer")
            return "-" if value is None else f"{value:.2f}"

        out.append(f"| {r['set']} | {'/'.join(t['languages'])} / {'/'.join(t['scripts'])} / {t['direction']} / {','.join(t['classes'])} "
                   f"| {proposed} | {r['right']} | {fmt('default')} | {fmt('seed')} | {fmt('vision')} | {best or '-'} | {found_text} | |")
    return head + "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", type=Path, required=True, help="a READ-ONLY copy of the Test Corpus (never the Pro's folder over a network mount)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pages", type=int, default=3, help="pages per set to read and score (3 to 5)")
    ap.add_argument("--arms", default="seed,vision", help="free arms to score: seed, vision")
    ap.add_argument("--only", default="", help="comma list of name fragments: run those sets only")
    ap.add_argument("--search", action="store_true", help="also run Set Up's model search per set (public queries)")
    ap.add_argument("--seed-reader", default="kraken-zenodo-21788410", help="catalogue id of the seeded multilingual reader")
    args = ap.parse_args()
    if not 1 <= args.pages <= 5:
        sys.exit("--pages is 1 to 5")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import ab_kraken_cloud as ab

    ab.require_scratch_state()
    os.environ.setdefault("FICHERO_APPLE_VISION_TIMEOUT", VISION_TIMEOUT_SECONDS)
    arms = [a for a in args.arms.split(",") if a]
    (args.out / "sets").mkdir(parents=True, exist_ok=True)
    rows = []
    for folder in sets_in(args.corpus, [o.strip() for o in args.only.split(",") if o.strip()]):
        truth = truth_for(folder.name)
        if truth is None:
            rows.append({"set": folder.name, "truth": dict(languages=["?"], scripts=["?"], direction="?", classes=["UNKNOWN-SET"]),
                         "proposed": {"refused": "no TRUTH row for this folder: add one"}, "right": "refused", "scores": {}})
            continue
        pages = pages_of(folder, args.pages)
        prop = proposal(truth)
        file_langs = sorted({lang for _, xml in pages if xml for lang in page_truth(xml)["languages"]})
        row = {"set": folder.name, "truth": truth, "file_languages": file_langs, "pages": [i.name for i, _ in pages],
               "proposed": prop, "right": judge(truth, prop), "scores": {}}
        for arm in arms:
            scores = read_pages(arm, pages, args.seed_reader)
            row["scores"][arm] = {"cer": mean(scores, "cer"), "wer": mean(scores, "wer"), "s_per_page": mean(
                [{"s": float(x["seconds"])} for x in scores if "seconds" in x], "s"), "pages": scores}
        reader = step_of(prop, "read-a-line")
        if reader.get("card") and "21788410" in str(reader["card"]) and "seed" in row["scores"]:
            row["scores"]["default"] = row["scores"]["seed"]  # the proposed reader IS the seed reader: same read
        if args.search:
            row["search"] = search_for(truth)
        (args.out / "sets" / f"{folder.name[:80].replace('/', '-')}.json").write_text(json.dumps(row, indent=1, default=str), encoding="utf-8")
        rows.append(row)
        print(f"| {folder.name}: {row['right']}; " + "; ".join(f"{a} CER {row['scores'][a]['cer']}" for a in row["scores"]) + " |", flush=True)
    (args.out / "matrix.json").write_text(json.dumps(rows, indent=1, default=str), encoding="utf-8")
    (args.out / "matrix.md").write_text(report(rows), encoding="utf-8")
    print(f"matrix: {args.out / 'matrix.md'} ({len(rows)} sets)")
    return 0


if __name__ == "__main__":
    # Leave by the engine's fast exit (#5929): with torch loaded, the ordinary exit runs MPS's static destructors, which fault
    # (SIGSEGV or abort) after the work is done, a finished run or a failed one alike.
    import traceback

    status = 1
    try:
        status = main()
    except SystemExit as stop:
        status = stop.code if isinstance(stop.code, int) else 1
        if isinstance(stop.code, str):
            print(stop.code, file=sys.stderr)
    except BaseException:  # noqa: BLE001 -- the failure is printed, then the process still leaves cleanly
        traceback.print_exc()
    from fichero_server.core import fast_exit

    fast_exit.leave(status)
    sys.exit(status)
