# Schemas kept with Fichero

`source.format.schemas-on-disk`: **validation never goes to the network.** So the schemas live
here, versioned with the code, and a missing one is a broken build rather than a silent pass
(`formats/__init__.py::validate` raises rather than returning "no problems").

Each file records where it came from, so a reader can check it against the published original and
so a licence review has something to review.

| File | Source | Fetched | Licence | Notes |
|---|---|---|---|---|
| `pagecontent-2019-07-15.xsd` | `https://www.primaresearch.org/schema/PAGE/gts/pagecontent/2019-07-15/pagecontent.xsd` | 2026-09-26 | **not audited**: the file carries no licence header; PRImA publishes it for public use | 85,826 bytes. `targetNamespace` `http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15`. PRImA Research's PAGE content schema — the format eScriptorium and Transkribus speak. Unmodified. |
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

| `alto-4-2.xsd` | `https://raw.githubusercontent.com/altoxml/schema/master/v4/alto-4-2.xsd` | 2026-09-26 | 54,450 bytes. ALTO 4.2. **Cannot be parsed offline yet**: it imports `http://www.loc.gov/standards/xlink/xlink.xsd`, and that file is not vendored. |
| `xml.xsd` | `https://www.w3.org/2001/xml.xsd` | 2026-09-26 | 8,836 bytes. The XML namespace's own schema, which xlink's imports. Correct and unmodified. |

**MISSING, and ALTO export refuses until it arrives:** the xlink schema ALTO names
(`http://www.loc.gov/standards/xlink/xlink.xsd`). **W3C's modern `xlink.xsd` is not a
substitute** — it defines `simpleAttrs` where ALTO references `simpleLink`, so mapping one to the
other builds a schema missing the definitions ALTO uses, and libxml2 refuses it. That substitution
was tried and removed: **a wrong mapping is worse than a missing one, because the error it produces
blames the document.** `loc.gov` returns 403 to a script, so this one needs a mirror or a manual
download.
