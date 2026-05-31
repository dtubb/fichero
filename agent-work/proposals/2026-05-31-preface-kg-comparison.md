# KG Comparison: Preface — "Shifting Livelihoods" (tubb2020shift)

**Date:** 2026-05-31  
**Analyst:** Agent read-only audit (no code edits)

---

## (a) Library + Document Identified

**Library (most recent Preface run):**  
`/Users/danieltubb/Documents/5 Fichero/CLI Preface+Ch1 Clean 20260523-063533.fichero`  
Created: 2026-05-23 06:35–06:36

**Document:**  
- Name: `tubb2020shift - Preface.pdf`  
- ID: `08d377eff2434939997122270773fedb`  
- File size: 282,635 bytes; text extracted: 41,268 chars

**All other libraries surveyed** (7 additional `.fichero` dirs including 2 kg-test libs, 2 older Preface+Ch1 runs, Batch Tiny+Medium, MediumTestLibrary) showed **zero KG entities, claims, citations, or non-transcription artifacts** on every document. The 20260523-063533 library is the most recent run of the Preface; it is the correct one to evaluate.

---

## (b) KG / Summary / Catalogue Actually Produced

### KG

| Metric | Count |
|--------|-------|
| `kg entities` (CLI) | **0** |
| `kg claims` (CLI) | **0** |
| `kg citations` (CLI) | **0** |
| `knowledgeentitys` rows (DuckDB direct) | **0** |
| `knowledgeclaims` rows (DuckDB direct) | **0** |
| `documentcitations` rows (DuckDB direct) | **0** |
| `references` rows (DuckDB direct) | **0** |

### Artifacts

| Type | Count | Notes |
|------|-------|-------|
| `transcription` | **55** | Apple Intelligence + Apple Vision OCR of each page-split doc; all belong to page-split child docs, **none** to the parent Preface doc `08d377ef` |
| `summary` | 0 | — |
| `catalogue` | 0 | — |
| Any other type | 0 | — |

The Preface parent document (`08d377ef`) has **zero artifacts of any kind**. The 55 transcription artifacts belong to the 15 page-split child docs (`fichero_upload_5t9kli57.pdf - Page 1` through `Page 15`) and appear to have been created by the Catalogue workflow's transcription node, not by a standalone transcription step on the parent.

### Workflow Runs

11 Catalogue workflow runs are recorded in `workflow_runs`:

| Status | Count | Key error |
|--------|-------|-----------|
| `failed` | 7 | Various (see below) |
| `running` (hung / never completed) | 4 | — |

**Failure modes observed:**

1. **Missing small model (2 runs, 2026-05-23):**  
   `"Workflow node uses $small but no default small model is configured. Set one in Settings → AI Defaults → Default small model"`  
   These fail in under 250ms — nothing is extracted at all.

2. **LLM connection error during Extract All Entities (5 runs, 2026-05-28 – 2026-05-29):**  
   `"ERROR processing 1: Connection error."` after ~52 seconds  
   The Extract All Entities node fires but the LLM call fails. Downstream Clean nodes run immediately and produce empty results (no entities to clean). The Write KG node completes but writes nothing. Finally: `"No aggregated text provided to catalogue tool"` — Catalogue step aborts.

**No workflow run ever completed successfully.** Zero KG entities or claims were ever written.

### CLI Bug Note

`fichero kg citations --doc <id>` crashes with `"No such option '--doc'"`. The correct invocation is positional: `fichero kg citations <doc_id>`. Same bug applies to `fichero artifacts list --doc <id>` → must be `fichero artifacts list <doc_id>`. These are undocumented breaking CLI argument changes; the `--doc` flag is advertised nowhere in `--help` but is commonly assumed from the `kg claims --doc` pattern that does work.

---

## (c) What the Real Chapter (Preface, pp. xv–xxiv) Actually Contains

The Preface of *Shifting Livelihoods: Gold Mining and Subsistence in the Chocó, Colombia* (Daniel Tubb, University of Washington Press, 2020) is a rich 10-page scholarly preface with dense entity content:

### Key People (named individuals)
- **Leidy** — primary interlocutor, artisanal gold miner, Afro-Colombian, Chocó
- **Martina** and **Pedro** — neighboring miners, key collaborators
- **Don Alfonso**, **Esteban** — village neighbors, miners
- **David Sánchez Juliao** — Colombian writer, author of short story "The Arrow" (epigraph source)
- **K. Sivaramakrishnan** — Series Editor, Yale University (Foreword author)
- **Kuntala Lahiri-Dutt** — scholar on gender and community livelihoods; coined "extractive peasants"

### Key Places
- **Chocó** — northwest Pacific region of Colombia; rain forests and rivers; site of fieldwork
- **Paimadó** — town being washed away by illegal Brazilian dredging operations (first met Leidy there, November 2010)
- **Bogotá** — capital; Gold Museum described
- **Lower Cauca**, **South of Bolívar**, **Nariño** — other Colombian regions affected by illegal mining
- **Antioquia** — neighboring province, source of outsider migrants to Chocó
- **Amazon** (1980s), **Venezuela** (1980s/2010s), **Peru's Madre de Dios**, **DRC**, **northern Myanmar**, **West Africa**, **Indonesia**, **Canadian Yukon**, **Alaska** — comparative global contexts
- **Andes Mountains**, **Atrato River basin** — geographic framing
- **City of London / River Thames** — where gold prices are set

### Key Organizations / Institutions
- **Constitutional Court of Colombia** — 2016 ruling granting the Atrato River legal personhood
- **Afro-Colombian peasant organizations** — granted Tubb research permission
- **University of Washington Press** — publisher
- **Yale University Agrarian Studies Program** — where book was drafted
- **Carleton University** (Ottawa) — Tubb's home institution
- **University of New Brunswick**, **Fredericton** — revisions completed here
- **Black community council** — gave Tubb identity card and collective territory access
- **Chocó Pacífico Mining Company** — early 20th century; provoked 1960s protest
- **Centro de Estudios para la Justicia Social (Tierra Digna)** — Colombian legal-justice NGO
- **Pontificia Universidad Javeriana** — Eduardo Restrepo's institution
- **Universidad Nacional de Colombia** — Claudia Mosquera Rosero-Labbé

### Key Concepts / Arguments
1. **Rebusque** — colloquial Colombian term for informal/shifting work; book's central analytical concept. Defined as temporary, contingent, creative, mobile informal labor. Draws on older English etymology of "shifting."
2. **Dual household economy** — artisanal mining as complement to subsistence farming (Part 1 argument)
3. **Cash economy and small-scale accumulation** — Part 2 (rebusque and cash)
4. **Value transformation (not creation)** — Part 3: gold launders drug money; speculative investment by Canadian mining corporations
5. **Gold as financial instrument** — ~171,300 metric tons globally; $8 trillion value; 52,000 metric tons still to mine; prices set by handful of London banks
6. **$1,900/troy oz gold price in 2011** — smashed records, reshaped life on Colombian rivers
7. **"Extractive peasants"** (Lahiri-Dutt's term) — millions worldwide mixing gold digging with farming, hunting, out-migration
8. **Simulated extraction / money laundering** — physical gold used to launder narco-money in Chocó
9. **Mercury contamination** — environmental disaster framing
10. **River personhood** — 2016 Atrato ruling

### Key Citations / Sources in Preface (footnotes 1–15 visible in PDF)
- Footnote 2: David Sánchez Juliao, "The Arrow" (epigraph)
- Footnote 4: Economic anthropology literature on Andean peasants (unnamed in preface text)
- Footnote 5: Apprenticeship in skilled techniques of mining (unnamed)
- Footnote 6: "This is a global phenomenon" — artisanal/small-scale mining (unnamed)
- Footnote 7: ~171,300 metric tons of gold; $8 trillion; 52,000 metric tons to mine (unnamed)
- Footnote 8: Prices set by banks on River Thames, City of London (unnamed)
- Footnote 9: Gold/silver from Colombia and Mexico were basis of Spanish colonial wealth (unnamed)
- Footnote 10: Colonial agricultural zones fed slave gangs in mining regions (unnamed)
- Footnotes 11–14: Various comparative global gold rush accounts
- Footnote 14: Kuntala Lahiri-Dutt on "extractive peasants"
- Footnote 15: "dual household economy" concept

---

## (d) Gap Analysis: Missing / Wrong / Empty

**Verdict: EMPTY.** The KG produced by the workflow is 100% empty — zero entities, zero claims, zero citations, zero summary, zero catalogue. This is a complete extraction failure, not sparseness.

### What the KG Should Contain vs. What It Does

| Category | Expected (from chapter) | Actual in KG |
|----------|------------------------|--------------|
| People entities | 6+ named individuals (Leidy, Martina, Pedro, David Sánchez Juliao, K. Sivaramakrishnan, Kuntala Lahiri-Dutt, + ~30 in Acknowledgments) | **0** |
| Place entities | 15+ (Chocó, Paimadó, Bogotá, Atrato River, Lower Cauca, Amazon, etc.) | **0** |
| Organization entities | 10+ (Constitutional Court, UW Press, Chocó Pacífico Mining Co., Tierra Digna, etc.) | **0** |
| Concept entities | 5+ (rebusque, dual household economy, extractive peasants, money laundering, value transformation) | **0** |
| Knowledge claims | 10+ arguable factual claims with footnotes | **0** |
| Citations / references | 15 footnotes in preface alone | **0** |
| Summary artifact | 1 | **0** |
| Catalogue artifact | 1 | **0** |

### Root Causes

**Primary cause — LLM connection error in Extract All Entities node:**  
All recent runs (2026-05-28 to 2026-05-29) fail with `"Connection error."` after ~52 seconds. This is a network/API timeout or authentication failure hitting the LLM provider during the entity extraction call. The workflow proceeds through downstream nodes but all of them receive empty inputs and write nothing.

**Secondary cause — missing small model config (earliest runs, 2026-05-23):**  
The Catalogue workflow has nodes requiring `$small` (a small/cheap LLM). These runs fail in <250ms before any LLM call because no default small model is configured in Settings. This is a configuration gap.

**Tertiary cause — no workflow ever completed successfully:**  
4 runs show `status=running` but have no `completed_at`. These are hung threads, not successful runs. The library contains no `running` workflow at the time of this audit — these are zombie records from previous sessions.

**Structural observation — parent doc has no artifacts:**  
The Catalogue workflow operates on page-split child documents (the 15 `fichero_upload_*.pdf - Page N` docs), not on the parent `tubb2020shift - Preface.pdf`. Even if the workflow succeeded, the parent doc would only get KG data if the workflow explicitly writes it back to the parent. This may be a second gap: transcription artifacts exist on child docs but the parent `08d377ef` has zero artifacts of any kind, including transcriptions.

---

## (e) Recommendations

### Immediate (block on running any further Preface analysis)

1. **Fix the LLM connection error (#278 / #279 / #881 family).**  
   The `"Connection error."` in the Extract All Entities node after 52 seconds is the primary blocker. Investigate: (a) which LLM provider/model is configured for this workflow's `extract_all` node, (b) whether it's an API key issue, rate limit, or network timeout, (c) add proper error surfacing so the user sees the actual HTTP error (not just "Connection error"). This is likely a timeout on a large context call — the page-split transcriptions total ~41K chars and may exceed model context or trigger a long-polling timeout.

2. **Configure a default small model** in Settings → AI Defaults → Default small model.  
   Without this, the `$small` nodes in the Catalogue workflow fail immediately on any library that hasn't set this explicitly.

### Structural / Architecture

3. **Confirm the KG write-back path for parent docs.**  
   If the Catalogue workflow extracts entities from page-split child docs but only writes KG rows scoped to the child `document_id`, the parent doc will show `kg_entities=0` forever even after a successful run. Verify whether `Write KG` maps extracted entities back to the parent. If not, this is a KG attribution bug (#881 family).

4. **Add a workflow run status CLI command.**  
   `fichero workflow threads` exists but `fichero workflow runs` does not. There is no way to list past run statuses or errors via CLI without querying DuckDB directly. A `fichero workflow log <thread_id>` or `fichero workflow runs list` command would make debugging much easier.

5. **Fix the CLI `--doc` flag bug.**  
   `fichero kg citations --doc <id>` and `fichero artifacts list --doc <id>` both fail with `"No such option '--doc'"`. These are positional arguments in the CLI, but the `--doc` pattern is natural and documented nowhere. Either add `--doc` as an alias or update the help text.

### Issue linkage

- Primary blocker: LLM connection error → **#278 / #279 / #881** (extraction gap / KG persistence family)  
- Small model config: **UI/settings gap** (likely covered under workflow configuration issues)  
- CLI `--doc` bug: new minor CLI bug, recommend filing  
- Parent doc KG attribution: possibly **#881** or a new issue
