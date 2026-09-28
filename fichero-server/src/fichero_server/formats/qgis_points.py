"""QGIS georeferencer `.points` files, in and out (#5122 maps C4; `source.geo.gcp-tables`).

    #CRS: <WKT of the map coordinates' CRS>          (optional line)
    mapX,mapY,sourceX,sourceY,enable,dX,dY,residual
    9.9301538,53.5814021,3899,-6412,1,...

One row per ground control point: the WORLD end (`mapX, mapY`, in the `#CRS`), the PIXEL end
(`sourceX, sourceY`: pixels from the image's top left, **y negative downwards**, QGIS's own
convention), whether it is used (`enable`), and QGIS's residuals.

* **The CRS is the file's, and never assumed** (`source.geo.crs-explicit`, `crs-unknown`): its
  top-level `AUTHORITY["EPSG", n]` names it; with no `#CRS` line the numbers are in whatever CRS
  the QGIS project had, which the file does not say -- so it is `unknown`, held unconverted
  (`models.geo`), never taken to be WGS 84 because the numbers look like degrees.
* **No image size is in the file.** With the page's size (the library supplies it at import) the
  pixel end becomes a normalised point; without one it is kept in `foreign["qgis:source"]` so a
  file-to-file round trip loses nothing.
* `enable` and QGIS's residuals have no field in the model: `enable` is kept in `foreign`; the
  residuals are worked out again from the GCPs (`source.geo.transform-is-derived`) and written as 0.
"""

from __future__ import annotations

import csv
import io
import re

from fichero_server.formats import register
from fichero_server.formats.harness import FormatSpec, LossReport, PageSegment, SourcePage

GCP_KIND = "control-point"
HEADER = ["mapX", "mapY", "sourceX", "sourceY", "enable", "dX", "dY", "residual"]
#: The world end's CRS and axis order, kept on the segment for the import (`models.geo`).
CRS_KEY = "gcp:crs"
AXIS_KEY = "gcp:axis_order"
#: EPSG:4326 as QGIS writes it in a `#CRS` line (WKT1), for our export.
WGS84_WKT = (
    'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],'
    'AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],'
    'UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]'
)
_AUTHORITY = re.compile(r'AUTHORITY\["EPSG",\s*"(\d+)"\]')


def _lines(data: bytes) -> list[str]:
    return data.decode("utf-8-sig").splitlines()


def _sniff(data: bytes) -> bool:
    try:
        lines = [line for line in _lines(data[:8192]) if line.strip()]
    except UnicodeDecodeError:
        return False
    header = next((line for line in lines if not line.startswith("#")), "")
    return [cell.strip() for cell in header.split(",")][:4] == HEADER[:4]


def crs_of(wkt: str | None) -> str:
    """`EPSG:n` from a WKT's TOP-LEVEL authority (the last one: inner ones name its datum, its
    ellipsoid, its unit), or `unknown` when the file states none."""
    found = _AUTHORITY.findall(wkt or "")
    return f"EPSG:{found[-1]}" if found else "unknown"


def read_points(data: bytes, image_size: tuple[int, int] | None = None) -> SourcePage:
    lines = _lines(data)
    wkt = next((line.split(":", 1)[1].strip() for line in lines if line.startswith("#CRS:")), None)
    crs = crs_of(wkt)
    geographic = crs in ("EPSG:4326", "unknown")
    rows = csv.DictReader(line for line in lines if line.strip() and not line.startswith("#"))
    page = SourcePage(image_size=image_size)
    if wkt:
        page.foreign["qgis:crs_wkt"] = wkt
    for index, row in enumerate(rows):
        x, y = float(row["sourceX"]), -float(row["sourceY"])        # QGIS: y negative downwards
        segment = PageSegment(kind=GCP_KIND, ref=f"gcp-{index}",
                              world=(float(row["mapX"]), float(row["mapY"])))
        if image_size:
            segment.point = [x / image_size[0], y / image_size[1]]
        else:
            segment.foreign["qgis:source"] = [x, y]
        segment.foreign[CRS_KEY] = crs
        # With no CRS stated the numbers' order is QGIS's (mapX first): recorded as such, not read
        # as longitude and latitude on a guess.
        segment.foreign[AXIS_KEY] = "lon,lat" if crs == "EPSG:4326" else "x,y"
        if (row.get("enable") or "1").strip() != "1":
            segment.foreign["qgis:enable"] = row.get("enable")
        page.segments.append(segment)
    if not geographic:
        page.foreign["qgis:projected"] = crs
    return page


def read(data: bytes) -> SourcePage:
    return read_points(data, None)


def write(page: SourcePage, report: LossReport) -> bytes:
    gcps = [s for s in page.segments if s.kind == GCP_KIND and s.world
            and (s.point is not None or s.foreign.get("qgis:source"))]
    others = [s for s in page.segments if s not in gcps]
    if others:
        report.note("segments other than control points with both ends", len(others),
                    "a .points file carries only ground control points")
    crs = {s.foreign.get(CRS_KEY, "EPSG:4326") for s in gcps}
    if len(crs) > 1:
        raise ValueError(f"the control points are in different CRSs ({', '.join(sorted(crs))}); a .points file has one")
    [only] = crs or {"EPSG:4326"}
    out = io.StringIO()
    if only == "EPSG:4326":
        out.write(f"#CRS: {WGS84_WKT}\n")
    elif page.foreign.get("qgis:crs_wkt"):
        out.write(f"#CRS: {page.foreign['qgis:crs_wkt']}\n")
    else:
        report.note("the CRS of the map coordinates", 1, f"it is {only}, and no WKT for it is held")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(HEADER)
    for s in gcps:
        if s.point is not None:
            if page.image_size is None:
                raise ValueError("a .points file needs pixels: the image's size is not known")
            x, y = s.point[0] * page.image_size[0], s.point[1] * page.image_size[1]
        else:
            x, y = s.foreign["qgis:source"]
        writer.writerow([_num(s.world[0]), _num(s.world[1]), _num(x), _num(-y),
                         s.foreign.get("qgis:enable", "1"), 0, 0, 0])
    return out.getvalue().encode("utf-8")


def _num(value: float) -> str:
    return f"{value:.10g}"


register(
    FormatSpec(
        name="qgis-points",
        extensions=(".points",),
        read=read,
        write=write,
        schema=None,
        round_trips=True,
        sniff=_sniff,
    )
)
