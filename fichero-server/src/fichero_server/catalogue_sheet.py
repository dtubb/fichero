"""The catalogue sheet: one row per folder, the columns of the rows' effective prototype (catalogue-export.md).

A template is a prototype's columns (`models/prototype_template.py`); this reads each folder's EFFECTIVE value
for them (`models/node_prototypes.effective_node_attributes`) and the computed columns from the folder and its
pages alone. Nothing is invented and no model is called: a cell with no value is empty.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from fichero_server.core.naturalsort import natural_key
from fichero_server.models import DocType, Document
from fichero_server.models.node_prototypes import (
    PrototypeResolutionError,
    effective_node_attributes,
    resolve_prototype_attributes,
)
from fichero_server.models.prototype_schema import level_defaults
from fichero_server.models.prototype_template import Column, Template, apply_choice, template_for_prototype, template_for_rows

_NOT_CATALOGUE_KINDS = frozenset({"workflow", "workflow_container", "workspace", "alias"})
SUFFIX = " Catalogación básica"
CHOICE_KEY = "column_choice"
_EDTF_START = re.compile(r"^(?P<y>-?\d{4})(?:-(?P<m>\d{2}))?(?:-(?P<d>\d{2}))?$")
_NUMBERED = re.compile(r"^(.*?)(\d+)$")


@dataclass
class Collection:
    """A node carrying a prototype for the folders beneath it (or the scope itself), and those folders."""

    name: str
    rows: list[Document] = field(default_factory=list)


def _sort_key(doc: Document) -> tuple:
    return (doc.sequence or 0, natural_key(doc.name))


def _children(db: Any, parent_id: str | None) -> list[Document]:
    found = db.query(Document, parent_id=parent_id) if parent_id else [d for d in db.all(Document) if d.parent_id is None]
    return sorted((d for d in found if d.deleted_at is None), key=_sort_key)


def _folders(db: Any, parent_id: str | None) -> list[Document]:
    return [d for d in _children(db, parent_id) if d.doc_type == DocType.folder and d.node_kind not in _NOT_CATALOGUE_KINDS]


def folders_under(db: Any, root: Document | None) -> list[Document]:
    """The folder itself, then every folder beneath it in sidebar order (a folder first, its subfolders after)."""
    out = [root] if root is not None else []

    def visit(parent_id: str | None) -> None:
        for child in _folders(db, parent_id):
            out.append(child)
            visit(child.id)

    visit(root.id if root is not None else None)
    return out


def pages_of(db: Any, folder: Document) -> list[Document]:
    """The folder's own pages in reading order."""
    return [d for d in _children(db, folder.id) if d.doc_type in (DocType.file, DocType.page) and d.node_kind != "workflow"]


def _is_collection(db: Any, doc: Document) -> bool:
    if not doc.prototype_key:
        return False
    try:
        return "subfolders" in level_defaults(resolve_prototype_attributes(db, doc.prototype_key))
    except PrototypeResolutionError:
        return False


def collections_in(db: Any, scope: Document | None) -> list[Collection]:
    """The scope's collections: a node whose prototype names the folders beneath it, each with the folders
    under it (a folder first, its subfolders after, in sidebar order); the scope itself when it holds none."""
    if scope is not None and scope.doc_type != DocType.folder:
        raise ValueError(f"Not a folder: {scope.name}")
    top = Collection(scope.name if scope is not None else "Library")
    found = [top]

    def visit(parent_id: str | None, current: Collection) -> None:
        for child in _folders(db, parent_id):
            if _is_collection(db, child):
                nested = Collection(child.name)
                found.append(nested)
                visit(child.id, nested)
            else:
                current.rows.append(child)
                visit(child.id, current)

    visit(scope.id if scope is not None else None, top)
    if not any(c.rows for c in found) and scope is not None and not _is_collection(db, scope):
        top.rows.append(scope)
    return [c for c in found if c.rows] or [top]


# --- the shared reads -------------------------------------------------------------------------------------


def image_ranges(stems: list[str]) -> str:
    """"IMG_017–IMG_019, IMG_025": stems ending in a number collapse where the numbers run on (one function
    for the Problemas clause and the Word transcript's list of blank pages)."""
    runs: list[list[str]] = []
    last: tuple[str, int] | None = None
    for stem in stems:
        m = _NUMBERED.match(stem)
        here = (m.group(1), int(m.group(2))) if m else None
        if runs and here and last and here[0] == last[0] and here[1] == last[1] + 1:
            runs[-1].append(stem)
        else:
            runs.append([stem])
        last = here
    return ", ".join(r[0] if len(r) == 1 else f"{r[0]}\u2013{r[-1]}" for r in runs)


def page_stem(page: Document) -> str:
    from fichero_server.page_export import export_stem

    return export_stem((page.metadata or {}).get("source_filename") or page.name, page.name)


def blank_pages(pages: list[Document]) -> list[Document]:
    from fichero_server.recipes.sorting import BLANK, KIND

    return [p for p in pages if (p.attributes or {}).get(KIND) == BLANK]


LISTS = ("catalogue_people", "catalogue_places", "catalogue_institutions")
#: The clauses a Faltantes row has: a gap in the numbering, a date nobody resolved, a name nobody confirmed.
GAP_CLAUSES = ("faltan ", "fecha sin normalizar", "fecha: ", "nombre sin confirmar")


def fold(text: Any) -> str:
    return unicodedata.normalize("NFC", str(text or "")).casefold().strip()


@dataclass
class Facts:
    """What the Problemas clauses read beyond the folder and its pages, read once per export: the graph's names
    (by folded canonical name and alias) and the statements a check rejected, by the document they stand on."""

    entities: dict[str, list[Any]] = field(default_factory=dict)
    rejected: dict[str, list[str]] = field(default_factory=dict)


def facts(db: Any) -> Facts:
    from fichero_server.models.checking import CheckVerdict
    from fichero_server.models.knowledge import EntityCurationState, KnowledgeClaim, KnowledgeEntity

    out = Facts()
    for entity in db.all(KnowledgeEntity):
        if entity.merged_into_id or entity.curation_state in (EntityCurationState.rejected, EntityCurationState.merged):
            continue
        for name in {entity.canonical_name, *entity.aliases}:
            out.entities.setdefault(fold(name), []).append(entity)
    latest: dict[str, Any] = {}
    for verdict in sorted(db.query(CheckVerdict, layer="claims"), key=lambda v: (v.created_at, v.id)):
        latest[verdict.target_id] = verdict
    for target, verdict in latest.items():
        claim = db.get(KnowledgeClaim, target) if verdict.verdict == "reject" else None
        if claim is not None and claim.source_document_id:
            out.rejected.setdefault(claim.source_document_id, []).append(claim.text)
    return out


def _listed(value: Any) -> list[str]:
    return [str(v) for v in (value if isinstance(value, list) else [value]) if v not in (None, "")]


def missing_numbers(stems: list[str]) -> list[str]:
    """The stems a numbered run lacks: "IMG_001, IMG_002, IMG_005" lacks IMG_003 and IMG_004 (padding as the run writes it)."""
    runs: dict[str, dict[int, int]] = {}
    for stem in stems:
        if m := _NUMBERED.match(stem):
            runs.setdefault(m.group(1), {})[int(m.group(2))] = len(m.group(2))
    out: list[str] = []
    for prefix, numbers in runs.items():
        width = max(numbers.values())
        out += [f"{prefix}{n:0{width}d}" for n in range(min(numbers), max(numbers)) if n not in numbers]
    return out


def _lint_flags(db: Any, folder: Document) -> list[str]:
    from fichero_server.recipes.catalogue_step import _latest

    art = _latest(db, folder.id)
    flags = (art.data or {}).get("lint_flags") if art is not None else None
    return [str(f) for f in flags] if isinstance(flags, list) else []


def _name_clauses(folder: Document, known: Facts) -> list[str]:
    from fichero_server.models.knowledge import EntityCurationState

    attrs = folder.attributes or {}
    typed = {fold(v) for key in LISTS for v in _listed(attrs.get(key))}
    out = [f"sin clasificar: {p}" for p in _listed(attrs.get("catalogue_access_points"))
           if fold(p) not in typed and fold(p) not in known.entities]
    unconfirmed = [n for key in LISTS for n in _listed(attrs.get(key))
                   if (found := known.entities.get(fold(n))) and all(e.curation_state == EntityCurationState.unreviewed for e in found)]
    if unconfirmed:
        out.append("nombre sin confirmar: " + "; ".join(dict.fromkeys(unconfirmed)))
    return out


def problems_for(db: Any, folder: Document, pages: list[Document], known: Facts | None = None) -> list[str]:
    """The folder's Problemas clauses: a person's own, then those computed from what the engine holds (never stored)."""
    from fichero_server.llm.working_lines import working_lines
    from fichero_server.recipes.catalogue_step import date_problems

    known = known or facts(db)
    own = (folder.attributes or {}).get("catalogue_problems")
    out = [str(x) for x in (own if isinstance(own, list) else [own] if own else [])]
    out.extend(date_problems(folder))
    blank = blank_pages(pages)
    if blank:
        out.append("en blanco: " + image_ranges([page_stem(p) for p in blank]))
    blank_ids = {p.id for p in blank}
    if unread := [page_stem(p) for p in pages if p.id not in blank_ids and working_lines(db, p.id) is None]:
        out.append("sin líneas: " + image_ranges(unread))
    if gaps := missing_numbers([page_stem(p) for p in pages]):
        out.append("faltan " + image_ranges(gaps))
    out.extend(_lint_flags(db, folder))
    out.extend(_name_clauses(folder, known))
    out.extend(f"declaración rechazada: {text}" for text in known.rejected.get(folder.id, []))
    for page in pages:
        out.extend(f"declaración rechazada: {text}" for text in known.rejected.get(page.id, []))
    return out


def render_date(value: Any, column: Column, lang: str = "es") -> str:
    """The START side of an EDTF value at its precision, in the column's format (`d/Mes/aaaa`); `?~%` dropped."""
    start = re.sub(r"[?~%]", "", str(value or "").split("/")[0]).strip()
    m = _EDTF_START.match(start)
    if not m:
        return ""
    year, month, day = m.group("y"), m.group("m"), m.group("d")
    if column.format != "d/Mes/aaaa":
        return start
    names = column.months.get(lang) or next(iter(column.months.values()), [])
    if not month or not names or not 1 <= int(month) <= len(names):
        return year
    name = names[int(month) - 1]
    return f"{int(day)}/{name}/{year}" if day else f"{name}/{year}"


def cataloguer(folder: Document) -> str:
    """Persons by name first, then each model as "Fichero (<model>)", each once, "; "."""
    from fichero_server.workflows.attribute_sources import BY_MACHINE, BY_PERSON, sources

    persons, models = [], []
    for source in sources(folder).values():
        if source.get("by") == BY_PERSON and source.get("name"):
            persons.append(str(source["name"]))
        elif source.get("by") == BY_MACHINE and source.get("model"):
            models.append(f"Fichero ({source['model']})")
    return "; ".join(dict.fromkeys([*persons, *models]))


def _description(db: Any, folder: Document) -> str:
    from fichero_server.recipes.catalogue_step import CONTENT_FROM, _latest

    if (folder.metadata or {}).get(CONTENT_FROM):
        return folder.page_content or ""
    art = _latest(db, folder.id)
    return (art.content or "") if art is not None else ""


def _list_cell(value: Any, column: Column) -> str:
    labels = column.option_labels.get("en", {})
    items = value if isinstance(value, list) else [value]
    return (column.join or "; ").join(str(labels.get(i, i)) for i in items if i not in (None, ""))


def cell(db: Any, folder: Document, column: Column, effective: dict[str, dict], lang: str = "es",
         known: Facts | None = None) -> str:
    if column.kind == "computed":
        pages = pages_of(db, folder)
        match column.source:
            case "folder.name":
                return folder.name
            case "folder.first_file":
                return page_stem(pages[0]) if pages else ""
            case "folder.last_file":
                return page_stem(pages[-1]) if pages else ""
            case "folder.page_count":
                return str(len(pages))
            case "description":
                return _description(db, folder)
            case "problems":
                return "; ".join(problems_for(db, folder, pages, known))
            case "cataloguer":
                return cataloguer(folder)
        return ""
    value = (effective.get(column.key) or {}).get("value")
    if value in (None, "", []):
        return ""
    if column.type == "date":
        return render_date(value, column, lang)
    return _list_cell(value, column)


def header_rows(columns: list[Column]) -> list[list[str]]:
    """The funder's English, the team's Spanish, then the instruction line; the key only when nothing is labelled."""
    rows = [[c.labels.get(lang, "") for c in columns] for lang in ("en", "es") if any(c.labels.get(lang) for c in columns)]
    if not rows:
        rows = [[c.label or c.key for c in columns]]
    if any(c.help for c in columns):
        rows.append([c.help.get("es") or next(iter(c.help.values()), "") for c in columns])
    return rows


def sheet_name(collection: str, used: set[str]) -> str:
    clean = re.sub(r"[\[\]:*?/\\]", " ", collection).strip() or "Catálogo"
    base = clean[: 31 - len(SUFFIX)] + SUFFIX
    name, n = base, 2
    while name.lower() in used:
        name = f"{base[:28]} {n}"
        n += 1
    used.add(name.lower())
    return name


def template_for(db: Any, scope: Document | None, rows: list[Document], prototype_key: str | None) -> Template:
    """A named prototype overrides; otherwise the rows' effective prototype (or union), narrowed by the scope's saved choice."""
    if prototype_key:
        return Template(template_for_prototype(db, prototype_key), prototypes=[prototype_key])
    choice = (scope.metadata or {}).get(CHOICE_KEY) if scope is not None else None
    return apply_choice(db, template_for_rows(db, rows), choice if isinstance(choice, dict) else None)


def grid(db: Any, template: Template, rows: list[Document], lang: str = "es") -> list[list[str]]:
    """The sheet's cells: the header rows, then one row per folder."""
    out = header_rows(template.columns)
    known = facts(db)
    for folder in rows:
        effective = effective_node_attributes(db, folder)
        out.append([cell(db, folder, c, effective, lang, known) for c in template.columns])
    return out


def subject_terms(template: Template) -> list[list[str]]:
    """The Tema sheet: the subject vocabulary, one row per term, English and Spanish."""
    column = next((c for c in template.columns if c.options and c.option_labels), None)
    if column is None:
        return []
    en, es = column.option_labels.get("en", {}), column.option_labels.get("es", {})
    return [[en.get(t, t), es.get(t, "")] for t in column.options]


# --- the other sheets (catalogue-export.md, "The sheets"): every cell text, read from the rows, the graph and the record ---

PROPOSALS = ("marked", "omitted")
_MARKED = {"confirmed": "confirmado", "proposed": "propuesto", "spacy": "propuesto (spaCy)"}


def _effective_list(db: Any, folder: Document, key: str) -> list[str]:
    return _listed((effective_node_attributes(db, folder).get(key) or {}).get("value"))


def faltantes(db: Any, template: Template, rows: list[Document], known: Facts, lang: str = "es") -> list[list[str]]:
    """The catalogue rows (same columns) whose Problemas names a gap, an unresolved date or an unconfirmed name,
    or that a person marked incomplete (`catalogue_incomplete`)."""
    out = header_rows(template.columns)
    for folder in rows:
        clauses = problems_for(db, folder, pages_of(db, folder), known)
        marked = (folder.attributes or {}).get("catalogue_incomplete") in (True, "true", "sí", "si")
        if marked or any(c.startswith(GAP_CLAUSES) for c in clauses):
            effective = effective_node_attributes(db, folder)
            out.append([cell(db, folder, c, effective, lang, known) for c in template.columns])
    return out


def _authority_state(entities: list[Any]) -> str:
    from fichero_server.models.knowledge import EntityCurationState

    verified = any(e.curation_state == EntityCurationState.verified for e in entities)
    return _MARKED["confirmed"] if verified else _MARKED["proposed"]


def authority_sheet(db: Any, rows: list[Document], key: str, known: Facts, proposals: str = "marked") -> list[list[str]]:
    """Personas, Lugares or Entidades: one row per distinct value of `key` across the rows, sorted, the graph's
    authority fields beside it, an instruction row under the headings, an empty Comentarios."""
    heads = {
        "catalogue_people": (["Forma en el catálogo", "Nombres", "Apellidos", "Información adicional", "Estado", "Carpetas",
                              "Comentarios"],
                             ["No editar: es la forma que imprimen las filas", "Del registro de la persona", "Del registro de la persona",
                              "Relación, cargo, viuda de…", "Confirmado o propuesto", "Carpetas que la nombran", "Escriba aquí"],
                             ("given_names", "surnames", "note")),
        "catalogue_places": (["Lugar en el catálogo", "Lugar canónico", "Tipo de lugar", "Dentro de", "Estado", "Carpetas",
                              "Comentarios"],
                             ["No editar: es la forma que imprimen las filas", "Del registro del lugar", "Del registro del lugar",
                              "Lugar que lo contiene", "Confirmado o propuesto", "Carpetas que lo nombran", "Escriba aquí"],
                             ("canonical", "place_type", "parent_place")),
        "catalogue_institutions": (["Entidad en el catálogo", "Forma canónica", "Estado", "Carpetas", "Comentarios"],
                                   ["No editar: es la forma que imprimen las filas", "Del registro de la entidad",
                                    "Confirmado o propuesto", "Carpetas que la nombran", "Escriba aquí"],
                                   ("canonical",)),
    }[key]
    names: dict[str, list[str]] = {}
    for folder in rows:
        for value in _effective_list(db, folder, key):
            names.setdefault(value, []).append(folder.name)
    out = [heads[0], heads[1]]
    for value in sorted(names, key=lambda v: (fold(v), v)):
        found = known.entities.get(fold(value), [])
        state = _authority_state(found) if found else _MARKED["proposed"]
        if proposals == "omitted" and state != _MARKED["confirmed"]:
            continue
        record = (found[0].metadata or {}) if found else {}
        fields = [(found[0].canonical_name if found else "") if f == "canonical" else str(record.get(f) or "")
                  for f in heads[2]]
        out.append([value, *fields, state, "; ".join(dict.fromkeys(names[value])), ""])
    return out


def catalogue_attributes(db: Any, rows: list[Document]) -> list[list[str]]:
    """Catálogo: one row per folder, every `catalogue_*` attribute as it stands (effective), alphabetically, the
    date text and its normalised form side by side."""
    values = {f.id: {k: v["value"] for k, v in effective_node_attributes(db, f).items()
                     if k.startswith("catalogue_") and v["value"] not in (None, "", [])} for f in rows}
    keys = sorted({k for v in values.values() for k in v})
    if "catalogue_dates" in keys and "catalogue_date_normalised" in keys:
        keys.remove("catalogue_date_normalised")
        keys.insert(keys.index("catalogue_dates") + 1, "catalogue_date_normalised")
    return [["Carpeta", *keys], *[[f.name, *["; ".join(_listed(values[f.id].get(k))) for k in keys]] for f in rows]]


def page_text(db: Any, page: Document) -> str:
    from fichero_server.api.routes.document.segment_readings import document_text

    try:
        derived = document_text(db, page.id)
    except LookupError:
        return page.page_content or ""
    return derived.text.strip() if derived.pass_id is not None else (page.page_content or "")


def pages_sheet(db: Any, rows: list[Document]) -> list[list[str]]:
    """Páginas: one row per page of the folders (their own pages): the folder, the file stem, the page's text."""
    return [["Carpeta", "Archivo", "Texto"],
            *[[f.name, page_stem(p), page_text(db, p)] for f in rows for p in pages_of(db, f)]]


def _maker(entity: Any) -> str:
    made = []
    for step in entity.attribution_chain:
        role = getattr(step.role, "value", step.role)
        if role == "editor" and step.name:
            made.append(step.name)
        elif role == "extractor":
            made.append("spaCy" if (step.name or "").lower() == "spacy" else f"Fichero ({step.label or step.name})")
    return "; ".join(dict.fromkeys(made))


def names_sheet(db: Any, rows: list[Document], proposals: str = "marked") -> list[list[str]]:
    """Nombres: the entities sourced on the rows' pages or descriptions, not rejected and not merged away, one row
    each: canonical name, forms as written, type, state, folders, who made it. A name only spaCy drafted is
    "propuesto (spaCy)" and appears only when proposals are asked for."""
    from fichero_server.models.knowledge import EntityCurationState, KnowledgeEntity

    owner: dict[str, str] = {}
    for folder in rows:
        owner[folder.id] = folder.name
        for page in pages_of(db, folder):
            owner[page.id] = folder.name
    out = [["Nombre canónico", "Formas escritas", "Tipo", "Estado", "Carpetas", "Hecho por"]]
    for entity in sorted(db.all(KnowledgeEntity), key=lambda e: (fold(e.canonical_name), e.id)):
        if entity.merged_into_id or entity.curation_state in (EntityCurationState.rejected, EntityCurationState.merged):
            continue
        folders = [owner[d] for d in entity.source_document_ids if d in owner]
        if not folders:
            continue
        maker = _maker(entity)
        if entity.curation_state == EntityCurationState.verified:
            state = _MARKED["confirmed"]
        else:
            state = _MARKED["spacy"] if maker in ("spaCy", "") else _MARKED["proposed"]
        if proposals == "omitted" and state != _MARKED["confirmed"]:
            continue
        forms = "; ".join(a for a in entity.aliases if a != entity.canonical_name)
        out.append([entity.canonical_name, forms, entity.entity_type.value, state, "; ".join(dict.fromkeys(folders)), maker])
    return out


def statements_sheet(db: Any, rows: list[Document]) -> list[list[str]]:
    """Declaraciones: the statements of the rows' pages: subject, verb, object, the page, the excerpt."""
    from fichero_server.models.knowledge import KnowledgeClaim

    pages = {p.id: p for f in rows for p in pages_of(db, f)}
    wanted = {*pages, *(f.id for f in rows)}
    claims = [c for c in db.all(KnowledgeClaim) if c.source_document_id in wanted]
    claims.sort(key=lambda c: (c.source_document_id or "", c.text.lower()))
    out = [["Sujeto", "Verbo", "Objeto", "Página", "Extracto"]]
    for c in claims:
        where = c.source_page_label or (pages[c.source_document_id].name if c.source_document_id in pages else "")
        out.append([c.subject_canonical or "", c.predicate_verb or "", c.object_phrase or "", where, c.source_excerpt or ""])
    return out


def notes_sheet(db: Any, rows: list[Document], proposals: str = "marked") -> list[list[str]]:
    """Notas: one row per folder and attribute key that has a source: by, step, run, when, what the model said, who
    accepted it; the parser's reading of a date is in what was said. A computed column has no source, so no row. A machine's
    proposal nobody answered is marked "propuesta sin responder" unless proposals are omitted."""
    out = [["Carpeta", "Campo", "Por", "Paso", "Ejecución", "Cuándo", "Dijo", "Aceptado por"]]
    for folder in rows:
        from fichero_server.workflows.attribute_sources import BY_MACHINE, proposals as held, pending, sources

        if proposals != "omitted":
            for key in sorted(held(folder)):
                if (waiting := pending(folder, key)) is not None:
                    src = waiting.get("source") or {}
                    out.append([folder.name, key, f"Fichero ({src.get('model')})" if src.get("model") else "Fichero",
                                str(src.get("step") or ""), str(src.get("run_id") or ""), str(waiting.get("proposed_at") or ""),
                                "propuesta sin responder: " + "; ".join(_listed(waiting.get("value"))), ""])
        for key, source in sorted(sources(folder).items()):
            machine = source.get("by") == BY_MACHINE
            by = f"Fichero ({source.get('model')})" if machine and source.get("model") else (
                "Fichero" if machine else str(source.get("name") or "persona"))
            said = str(source.get("said") or "")
            if check := source.get("date_check"):
                said = "; ".join(x for x in (said, f"analizador: {check.get('parser')}", f"modelo: {check.get('model')}") if x)
            out.append([folder.name, key, by, str(source.get("step") or ""), str(source.get("run_id") or ""),
                        str(source.get("at") or ""), said, str(source.get("accepted_by") or "")])
    return out


def workbook(db: Any, scope: Document | None, prototype_key: str | None = None, proposals: str = "marked") -> dict[str, tuple[list[list[str]], int]]:
    """The whole workbook as {sheet name: (rows, frozen header rows)}, in the spec's order: a catalogue sheet per
    collection, then Faltantes, Personas, Lugares, Entidades, Tema, Catálogo, Páginas, Nombres, Declaraciones, Notas.
    A sheet with no rows keeps its header. Reads attributes, pages, the graph and the record; never a model."""
    if proposals not in PROPOSALS:
        raise ValueError(f"proposals is one of {', '.join(PROPOSALS)}; not {proposals!r}")
    known = facts(db)
    sheets: dict[str, tuple[list[list[str]], int]] = {}
    names: set[str] = set()
    every: list[Document] = []
    tema: list[list[str]] = []
    for collection in collections_in(db, scope):
        template = template_for(db, scope, collection.rows, prototype_key)
        cells = grid(db, template, collection.rows)
        sheets[sheet_name(collection.name, names)] = (cells, len(cells) - len(collection.rows))
        every += collection.rows
        tema = tema or subject_terms(template)
    template = template_for(db, scope, every, prototype_key)
    missing = faltantes(db, template, every, known)
    sheets["Faltantes"] = (missing, len(header_rows(template.columns)))
    for name, key in (("Personas", "catalogue_people"), ("Lugares", "catalogue_places"), ("Entidades", "catalogue_institutions")):
        sheets[name] = (authority_sheet(db, every, key, known, proposals), 2)
    sheets["Tema"] = ([["Related Subjects", "Tema"], *tema], 1)
    sheets["Catálogo"] = (catalogue_attributes(db, every), 1)
    sheets["Páginas"] = (pages_sheet(db, every), 1)
    sheets["Nombres"] = (names_sheet(db, every, proposals), 1)
    sheets["Declaraciones"] = (statements_sheet(db, every), 1)
    sheets["Notas"] = (notes_sheet(db, every, proposals), 1)
    return sheets
