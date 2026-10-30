"""Builders for folders and pages, and a reader for the .xlsx the catalogue export writes."""
import zipfile
from xml.etree import ElementTree as ET

from fichero_server.models import DocType, Document

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def folder(db, name, parent=None, proto=None, attrs=None, meta=None, seq=None, content=None):
    doc = Document(name=name, path=f"/{name}", doc_type=DocType.folder, parent_id=parent, prototype_key=proto,
                   attributes=attrs or {}, metadata=meta or {}, sequence=seq, page_content=content)
    db.save(doc)
    return doc


def page(db, name, parent, attrs=None, meta=None, seq=None):
    doc = Document(name=name, path=f"/{name}", doc_type=DocType.page, parent_id=parent, attributes=attrs or {},
                   metadata=meta or {}, sequence=seq)
    db.save(doc)
    return doc


def read_xlsx(path):
    """{sheet name: [[cell text]]} and {sheet name: frozen rows}."""
    with zipfile.ZipFile(path) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        out, frozen = {}, {}
        for i, sheet in enumerate(wb.find("m:sheets", NS), start=1):
            root = ET.fromstring(z.read(f"xl/worksheets/sheet{i}.xml"))
            pane = root.find(".//m:pane", NS)
            frozen[sheet.get("name")] = int(pane.get("ySplit")) if pane is not None else 0
            rows = []
            for row in root.iter(f"{{{NS['m']}}}row"):
                cells = {}
                for c in row:
                    letters = "".join(ch for ch in c.get("r") if ch.isalpha())
                    n = 0
                    for ch in letters:
                        n = n * 26 + ord(ch) - 64
                    cells[n] = "".join(t.text or "" for t in c.iter(f"{{{NS['m']}}}t"))
                rows.append(cells)
            width = max((max(r, default=0) for r in rows), default=0)  # empty cells are not written: pad to the sheet's width
            out[sheet.get("name")] = [[r.get(k, "") for k in range(1, width + 1)] for r in rows]
        return out, frozen
