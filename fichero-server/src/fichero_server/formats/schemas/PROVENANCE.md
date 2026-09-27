# Schemas kept with Fichero

`source.format.schemas-on-disk`: **validation never goes to the network.** So the schemas live
here, versioned with the code, and a missing one is a broken build rather than a silent pass
(`formats/__init__.py::validate` raises rather than returning "no problems").

Each file records where it came from, so a reader can check it against the published original and
so a licence review has something to review.

| File | Source | Fetched | Licence | Notes |
|---|---|---|---|---|
| `pagecontent-2019-07-15.xsd` | `https://www.primaresearch.org/schema/PAGE/gts/pagecontent/2019-07-15/pagecontent.xsd` | 2026-09-26 | Apache-2.0 (PRImA-Research-Lab/PAGE-XML repository licence; the file itself carries no header). Checked 2026-09-27: byte-identical to `PAGE-release/gts/pagecontent/2019-07-15/pagecontent.xsd` in that repository | 85,826 bytes. `targetNamespace` `http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15`. PRImA Research's PAGE content schema — the format eScriptorium and Transkribus speak. Unmodified. |
| `tei_all.xsd` | `https://tei-c.org/release/xml/tei/custom/schema/xsd/tei_all.xsd` | 2026-09-26 | CC BY 3.0 or BSD-2-Clause (the file's own header; TEI Consortium) | 1,084,908 bytes. `targetNamespace` `http://www.tei-c.org/ns/1.0`. TEI P5 4.12.0 (generated from the ODD 2026-07-28), the full `tei_all` customisation -- the widest schema, so an export is valid TEI and not valid only against our own subset. Unmodified. |
| `tei_all_teix.xsd` | same directory | 2026-09-26 | as `tei_all.xsd` (TEI Consortium) | 2,167 bytes. Imported by `tei_all.xsd` for the TEI Examples namespace; must sit beside it. Unmodified. |
| `tei_all_xml.xsd` | same directory | 2026-09-26 | as `tei_all.xsd` (TEI Consortium) | 2,305 bytes. Imported by `tei_all.xsd` for the `xml:` attributes (`xml:id`, `xml:lang`); must sit beside it. Unmodified. |

The TEI schema is compiled once per process (`validation.py::_compiled`): it is 1 MB and compiling
it took seven seconds.

**Adding one:** fetch it once, record it in this table with its licence, size and target namespace, and never
edit it. A schema edited to make our output validate is a schema that no longer says what the format
is — and the whole point of validating is that somebody else's tool will read the file.

**Fetching at build or run time is not an option.** A validator that reaches the network fails in a
sandbox, fails offline, and can be pointed somewhere else by a document; all three are worse than a
file in the repository.

| `alto-4-2.xsd` | `https://raw.githubusercontent.com/altoxml/schema/master/v4/alto-4-2.xsd` | 2026-09-26 | 54,450 bytes. ALTO 4.2. It imports `http://www.loc.gov/standards/xlink/xlink.xsd`, which resolves to the vendored `xlink.xsd` below. Licence: **CC BY-SA 4.0, stated in the file's own header** (the ALTO Editorial Board waives its rights). An earlier note here said the header stated none; it was wrong, and read nobody's file. Checked 2026-09-27: byte-identical to `v4/alto-4-2.xsd` in altoxml/schema. |
| `alto-4-3.xsd` | `https://github.com/altoxml/schema/blob/master/v4/alto-4-3.xsd` (via the GitHub API) | 2026-09-27 | 61,351 bytes. ALTO 4.3, which adds `ReadingOrder` and is what Kraken writes. Same namespace as 4.2 (`ns-v4#`), so a file says which by the schema file it declares. Imports xlink as 4.2 does. Licence: CC BY-SA 4.0, stated in its header; redistributed unmodified with that header, which is what attribution needs. Used by `scripts/validate_exports.py` for files that declare it; exports are still written as 4.2. Unmodified. sha256 `03b83230012810f9ba616b11ad63aad3105f69b34622f05089fae5efffe47345`. |
| `alto-4-4.xsd` | `https://github.com/altoxml/schema/blob/master/v4/alto-4-4.xsd` (via the GitHub API) | 2026-09-27 | 63,830 bytes. ALTO 4.4, the current release. It adds `LANG`, `ROTATION` and `OTHERLANGS` on `Page`, which is what Kraken's files use even though they declare 4.3. Imports xlink as 4.2 does. Licence: CC BY-SA 4.0, stated in its header. Used by `scripts/validate_exports.py` for files that declare it. Unmodified. sha256 `2d1ba4b0ce268c4ed763f718cfb9b1ab67ac952caf5bcffa5fc314179cb0866b`. |
| `pagecontent-2013-07-15.xsd` | `PRImA-Research-Lab/PAGE-XML`, `PAGE-release/gts/pagecontent/2013-07-15/pagecontent.xsd` (via the GitHub API) | 2026-09-27 | 51,333 bytes. `targetNamespace` `http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15`, which is what Transkribus writes and what three of our real fixtures are. Licence: Apache-2.0 (the repository's). Imports nothing. Used by `scripts/validate_exports.py` for files in that namespace; exports are still written as 2019. Unmodified. sha256 `cda86e6680711663ae8788a3f17959aa12c765ca3798b5d6356313ca5980573d`. |
| `xml.xsd` | `https://www.w3.org/2001/xml.xsd` | 2026-09-26 | 8,836 bytes. The XML namespace's own schema, which xlink's imports. Correct and unmodified. |
| `xlink.xsd` | `https://raw.githubusercontent.com/OCR-D/core/master/src/ocrd_validators/xlink.xsd` (OCR-D/core, Apache-2.0) | 2026-09-26 | 3,180 bytes. The METS XLink schema v2 (Nov 2004), which is what `http://www.loc.gov/standards/xlink/xlink.xsd` serves and what ALTO's XSD imports by that URL. Defines `attributeGroup simpleLink`, which ALTO references (checked by grep before vendoring). Unmodified. Licence: it is LOC's schema, redistributed here from OCR-D's Apache-2.0 repository; LOC's own terms were not audited. **Provenance caveat:** `loc.gov` returns 403 to a script, so this copy could not be byte-compared with the original. |

**The wrong file to vendor instead:** W3C's modern `xlink.xsd` defines `simpleAttrs` where ALTO references
`simpleLink`; mapping it in builds a schema missing the definitions ALTO uses, and libxml2 refuses it.
`validation.py::VENDORED_IMPORTS` maps LOC's URL to `xlink.xsd` and nothing else, and raises
(`UnvendoredSchemaImport`) for any other absolute import.

**Not vendored: ALTO 2.x** (`alto-2-0.xsd`, `alto-2-1.xsd` in altoxml/schema `v2/`). Neither file states a
licence, and the repository has no licence file. The 4.x files carry CC BY-SA 4.0 in their headers; the v2
files do not. A schema we may not redistribute is worse than none, so an ALTO 2 file is reported as
*other version* (checked by nothing) until a licence is found. Checked 2026-09-27.
