# Document Processing Steps - Plain English Translation

## Step 1: Extract People, Organizations & Locations
**What it does:** Looks through the documents and finds:
- People (full names, titles, roles)
- Organizations (companies, institutions, agencies) 
- Locations (cities, states, countries, addresses)

**Instructions to AI:** "You are analyzing a collection of documents. Extract named entities from these pages. For each entity found, note any available context. Include alternative spellings.

Identify and classify:
- People (full names, titles, roles, etc.)
- Organizations (companies, institutions, agencies, etc.)
- Locations (cities, states, countries, addresses, etc.)

IMPORTANT:
- Include ALL occurrences, but do not include page numbers.
- Preserve exact spelling and names, but capitalize names properly. Include alternative spellings, but combine into one entry with the best spelling first.
- Include context when available and well-supported.
- Write all context in English.

Return as JSON with these exact keys:
- people: [name, alternative_spellings, context]
- organizations: [name, alternative_spellings, context]  
- locations: [name, alternative_spellings, context]

Return ONLY valid JSON. Say nothing else."

---

## Step 2: Extract Dates, Legal References & Rivers
**What it does:** Finds and organizes:
- Dates (specific dates, date ranges, years)
- Legal References (case numbers, statutes, regulations)
- Rivers (river names, tributaries, waterways)

**Instructions to AI:** "You are analyzing a collection of documents. Extract named entities from these pages. For each entity found, note any available context. Include alternative spellings.

Identify and classify:
- Dates (specific dates, date ranges, years, etc.)
- Legal References (case numbers, statutes, regulations, etc.)
- Rivers (river names, tributaries, waterways, etc.)

IMPORTANT:
- Include ALL occurrences, but do not include page numbers.
- Preserve exact spelling and names, but capitalize names properly. Include alternative spellings, but combine into one entry with the best spelling first.
- Include context when available and well-supported.
- Include normalized dates, such as YYYY-MM-DD.
- Write all context in English.

Return as JSON with these exact keys:
- dates: [date, normalized_date, context]
- legal_references: [name, context]
- rivers: [name, alternative_spellings, context]

Return ONLY valid JSON. Say nothing else."

---

## Step 3: Extract Specialized Entities
**What it does:** Looks for specific types of information:
- Key Events (meetings, incidents, transactions)
- Mines (mine names, mining claims, shafts)
- Properties (estates, parcels, lots, buildings)
- Dredges (dredge names, types, registration numbers)
- Animals (species, breeds, livestock, notable individual animals)
- Plants (species, varieties, crops, notable individual plants)
- Weapons (types, models, serial numbers, named weapons)
- Injuries (injury types, wounds, medical conditions)

**Instructions to AI:** "You are analyzing a collection of documents. Extract named entities from these pages. For each entity found, note any available context. Include alternative spellings.

Identify and classify:
- Key Events (meetings, incidents, transactions, etc.)
- Mines (mine names, mining claims, shafts, etc.)
- Properties (estates, parcels, lots, buildings, etc.)
- Dredges (dredge names, types, registration numbers, etc.)
- Animals (species, breeds, livestock, notable individual animals, etc.)
- Plants (species, varieties, crops, notable individual plants, etc.)
- Weapons (types, models, serial numbers, named weapons, etc.)
- Injuries (injury types, wounds, medical conditions, etc.)

IMPORTANT:
- Include ALL occurrences, but do not include page numbers.
- Preserve exact spelling and names, but capitalize names properly. Include alternative spellings, but combine into one entry with the best spelling first.
- Include context when available and well-supported.
- Write all context in English.

Return as JSON with these exact keys:
- key_events: [event, context]
- mines: [name, context]
- properties: [name, alternative_spellings, context]
- dredges: [name, context]
- animals: [name, alternative_spellings, context]
- plants: [name, context]
- weapons: [name, alternative_spellings, context]
- injuries: [name, alternative_spellings, context]

Return ONLY valid JSON. Say nothing else."

---

## Step 4: Create Timeline
**What it does:** Uses the NER results and transcription to create a chronological timeline of important events.

**Instructions to AI:** "Using the NER results and the transcription with page numbers, create a chronological timeline of the most important events. For each event:
- Include the date (normalized as YYYY-MM-DD when possible)
- Describe the event concisely
- Do not include page numbers.
- Write all event descriptions in English

Return as JSON with this exact format:
- timeline: [date, event]

Return ONLY valid JSON. Do not include any other text."

---

## Step 5: Identify Key People & Tags
**What it does:** Identifies the most important people and creates descriptive tags for the document.

**Instructions to AI:** "Using these materials:
1. Original transcription with page numbers
2. Named Entity Recognition (NER) results
3. Event timeline

Identify the most important people in this case and generate descriptive tags/keywords for the document.

Identify:
- The 5-10 most important people mentioned in the case
- 5-10 descriptive tags/keywords that capture the main themes, subjects, locations, etc.

For key people, include their role and importance in the case (what they did). For tags, focus on legal themes, geographical locations, industries, time periods, and key concepts.

Write all descriptions in English.

Return as JSON with this exact format:
- key_people: [name, context]
- tags: "tag1; tag2; tag3; tag4; tag5; tag6; tag7; tag8; tag9; tag10"

Return ONLY valid JSON. Do not include any other text."

---

## Step 6: Create Summary
**What it does:** Creates a 150-word summary suitable for archival description.

**Instructions to AI:** "Using these materials:
1. Original transcription with page numbers
2. Named Entity Recognition data:
   - People, organizations and locations
   - Dates, legal references and rivers
   - Specialized entities (key events, mines, properties, dredges, animals, plants, weapons, injuries)
3. Event timeline
4. Key people and descriptive tags

Create a concise 150-word summary in clear English, suitable for archival description, while providing a coherent overview of the case. Include essential people, places, dates and events. Do not include your own analysis. Do not invent or include details beyond what is explicitly provided in the materials.

Return as JSON exactly in this format:
- summary: "[150-word summary in English]"

Return ONLY valid JSON. Do not include any other text."

---

## Technical Settings
- **Model used for steps 1-5:** GPT-4.1 Mini
- **Model used for step 6 (summary):** GPT-4.1
- **Temperature:** 0.0 (for consistent results)
- **Max tokens:** 1,000,000
- **Timeout:** 120 seconds per step
- **Retry attempts:** 3
- **Retry delay:** 5 seconds 