# Costed estimate across all 39 presets — #4501 phase 2, #4503

Produced by `workflows/provider_preview.py`. **Nothing was executed and no provider was contacted.**

The same 39 files, resolved against two databases:

| configuration | free presets | not free |
|---|---|---|
| factory defaults (what a NEW install gets) | **38 of 39** | 1 |
| this machine's app DB (openrouter/gemini-3-flash) | **14 of 39** | 25 |

That is the whole finding in one table. Identical presets, opposite answers,
because the answer lives in the database and not in the file.

Total model calls per page across all 39 presets: **61**.

```

########## FACTORY DEFAULTS (on-device) — what a NEW INSTALL gets ##########
FREE: 38   NOT-FREE: 1   (of 39)

preset                                         nodes  model billable  surprise calls/page
1 · Import → Artifacts                             2      0        0         0          -  -
2 · Extract Entities                               2      1        0         0          1  apple
3 · Extract SVO → Claims                           2      1        0         0          1  apple
4 · Merge / Dedup                                  2      0        0         0          -  -
5 · KG Persist / Finalize                          2      0        0         0          -  -
6 · Catalogue                                      2      1        0         0          1  apple
Capture OCR + Transcribe                           4      1        0         0          1  apple
Catalogue                                         12     10        0         0         10  apple
Clean Up Text                                      3      2        0         0          2  apple
Convert to HTML                                    2      1        0         0          1  apple
Convert to Markdown                                2      1        0         0          1  apple
Convert to SVG                                     2      1        0         0          1  apple
Describe (visual)                                  2      1        0         0          1  apple
Enhance Images                                     2      0        0         0          -  -
Export to Desktop (MD + DOCX + XLSX)               2      0        0         0          -  -
Extract Geo                                        3      2        0         0          2  apple
Extract Table                                      2      1        0         0          1  apple
Fuzzy Clean Images                                 2      0        0         0          -  -
Group Same Documents                               3      1        0         0          1  apple
NER per-page (local)                               3      1        0         0          1  apple
Prepare Images for OCR                             2      0        0         0          -  -
Recombine Segments                                 2      0        0         0          -  -
Remove Background Images                           2      0        0         0          -  -
Rotate / Auto-Orient Images                        2      0        0         0          -  -
Segment Images                                     2      0        0         0          -  -
Spanish Script v2 Child Passes (19th-20th C.)      4      3        0         0          3  apple
Split Chapters                                     2      0        0         0          -  -
Split Images                                       2      0        0         0          -  -
Transcribe                                         2      1        0         0          1  apple
Transcribe (Auto-Detect)                          10      7        0         0          7  apple
Transcribe HTR                                     4      2        0         0          2  apple
Transcribe Manuscript                              2      1        0         0          1  apple
Transcribe Paleography                             4      2        0         0          2  apple
Transcribe Paleography (Ensemble + Deep Review     9      6        0         0         12  apple
Transcribe Spanish Script (19th-20th C.)           2      0        0         0          -  -
Transcribe Typescript                              2      1        0         0          1  apple
Translate                                          3      2        0         0          2  apple
Translate (DeepL)                                  3      2        1         0          2  apple,deepl
Translate + Double-Check                           4      3        0         0          3  apple

TOTAL calls/page across all presets: 61

########## THIS MACHINE's app DB (openrouter/gemini-3-flash) ##########
FREE: 14   NOT-FREE: 25   (of 39)

preset                                         nodes  model billable  surprise calls/page
1 · Import → Artifacts                             2      0        0         0          -  -
2 · Extract Entities                               2      1        1         1          1  openrouter
3 · Extract SVO → Claims                           2      1        1         1          1  openrouter
4 · Merge / Dedup                                  2      0        0         0          -  -
5 · KG Persist / Finalize                          2      0        0         0          -  -
6 · Catalogue                                      2      1        1         1          1  openrouter
Capture OCR + Transcribe                           4      1        1         1          1  openrouter
Catalogue                                         12     10       10        10         10  openrouter
Clean Up Text                                      3      2        2         2          2  openrouter
Convert to HTML                                    2      1        1         1          1  openrouter
Convert to Markdown                                2      1        1         1          1  openrouter
Convert to SVG                                     2      1        1         1          1  openrouter
Describe (visual)                                  2      1        1         1          1  openrouter
Enhance Images                                     2      0        0         0          -  -
Export to Desktop (MD + DOCX + XLSX)               2      0        0         0          -  -
Extract Geo                                        3      2        2         2          2  openrouter
Extract Table                                      2      1        1         1          1  openrouter
Fuzzy Clean Images                                 2      0        0         0          -  -
Group Same Documents                               3      1        1         1          1  openrouter
NER per-page (local)                               3      1        1         1          1  openrouter
Prepare Images for OCR                             2      0        0         0          -  -
Recombine Segments                                 2      0        0         0          -  -
Remove Background Images                           2      0        0         0          -  -
Rotate / Auto-Orient Images                        2      0        0         0          -  -
Segment Images                                     2      0        0         0          -  -
Spanish Script v2 Child Passes (19th-20th C.)      4      3        3         3          3  openrouter
Split Chapters                                     2      0        0         0          -  -
Split Images                                       2      0        0         0          -  -
Transcribe                                         2      1        1         1          1  openrouter
Transcribe (Auto-Detect)                          10      7        7         7          7  openrouter
Transcribe HTR                                     4      2        2         2          2  openrouter
Transcribe Manuscript                              2      1        1         1          1  openrouter
Transcribe Paleography                             4      2        2         2          2  openrouter
Transcribe Paleography (Ensemble + Deep Review     9      6        6         6         12  openrouter
Transcribe Spanish Script (19th-20th C.)           2      0        0         0          -  -
Transcribe Typescript                              2      1        1         1          1  openrouter
Translate                                          3      2        2         2          2  openrouter
Translate (DeepL)                                  3      2        2         1          2  deepl,openrouter
Translate + Double-Check                           4      3        3         3          3  openrouter

TOTAL calls/page across all presets: 61
```
