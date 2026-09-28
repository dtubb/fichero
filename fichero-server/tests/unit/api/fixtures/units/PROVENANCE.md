# Unit conversions -- provenance

Every conversion in `fichero_server/knowledge/units.py` that says it is VERIFIED is checked by
`tests/unit/api/test_the_unit_values_are_the_recorded_ones.py` against the text recorded here. A
conversion with no recorded source says "cited, not verified" in every answer that uses it.

| File | Source | Licence | Recorded | What it records |
|---|---|---|---|---|
| `nist_hb44_2024_appendix_c.json` | NIST Handbook 44, 2024 Edition, Appendix C "General Tables of Units of Measurement", pages C-5, C-10, C-11: `https://nvlpubs.nist.gov/nistpubs/hb/2024/NIST.HB.44-2024.pdf`, text via `pdftotext -layout`; the lines quoted verbatim | US government work, public domain (17 U.S.C. 105) | 2026-09-28 | The statute mile (5280 feet; 1609.344 m), the international foot (0.3048 m exactly) and the league (3 miles; 4 828.032 m). |
| `esbe_versta.json` | Энциклопедический словарь Брокгауза и Ефрона (1890-1907), s.v. «Верста», as transcribed on Russian Wikisource, page ЭСБЕ/Верста, revision 2312560 (2016-08-06); the sentence quoted verbatim | Public domain (published 1890-1907) | 2026-09-28 | "Нынешняя верста в 500 саженей равна 1066,781 метр." -- the verst of 500 sazhen after the 1835 reform, 1066.781 m. |

**Not found, so not verified:** the Castilian vara's metric equivalence (0.835905 m, the value cited
for the 1849 Spanish metric law and its tables of equivalence) -- neither the Gaceta de Madrid text
nor the 1852 tables could be retrieved as text here. `legua` and `vara` carry `verified: false` and
say "cited, not verified" in the answer.
