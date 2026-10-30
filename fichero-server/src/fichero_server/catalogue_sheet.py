"""The catalogue sheet: one row per folder, the columns of the rows' effective prototype (catalogue-export.md).

A template is a prototype's columns (`models/prototype_template.py`); this reads each folder's EFFECTIVE value
for them (`models/node_prototypes.effective_node_attributes`) and the computed columns from the folder and its
pages alone. Nothing is invented and no model is called: a cell with no value is empty.
"""
from __future__ import annotations

import re
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


def problems_for(db: Any, folder: Document, pages: list[Document]) -> list[str]:
    """The folder's Problemas clauses: a person's own, then those computed from what the engine holds."""
    from fichero_server.recipes.catalogue_step import date_problems

    own = (folder.attributes or {}).get("catalogue_problems")
    out = [str(x) for x in (own if isinstance(own, list) else [own] if own else [])]
    out.extend(date_problems(folder))
    if blank := blank_pages(pages):
        out.append("en blanco: " + image_ranges([page_stem(p) for p in blank]))
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


def cell(db: Any, folder: Document, column: Column, effective: dict[str, dict], lang: str = "es") -> str:
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
                return "; ".join(problems_for(db, folder, pages))
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
    for folder in rows:
        effective = effective_node_attributes(db, folder)
        out.append([cell(db, folder, c, effective, lang) for c in template.columns])
    return out


def subject_terms(template: Template) -> list[list[str]]:
    """The Tema sheet: the subject vocabulary, one row per term, English and Spanish."""
    column = next((c for c in template.columns if c.options and c.option_labels), None)
    if column is None:
        return []
    en, es = column.option_labels.get("en", {}), column.option_labels.get("es", {})
    return [[en.get(t, t), es.get(t, "")] for t in column.options]
