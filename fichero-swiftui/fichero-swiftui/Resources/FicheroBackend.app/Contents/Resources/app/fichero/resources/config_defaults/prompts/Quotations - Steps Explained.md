# Quotation Extraction Steps - Plain English Translation

## Step 1: Extract People Names
**What it does:** Identifies all unique names of people mentioned in the documents, focusing on witnesses and parties.

**Instructions to AI:** "You are analyzing a collection of documents. Extract all unique names of people mentioned in these pages. For each person found, note any available context about their role or title.

IMPORTANT:
- Include ALL unique names of people mentioned.
- Preserve exact spelling and names, but capitalize names properly.
- For each person, identify the most common/standard spelling and list any variations as alternatives.
- Include context when available (titles, roles, etc.).
- Focus on witnesses, parties, and people giving testimony - not judges or court officials unless they are also witnesses.
- Do not include page numbers in this step.
- If you find multiple spellings of the same name, choose the most complete/formal version as the primary name.

Return as JSON with these exact keys:
- people: [name, alternative_spellings, context]

Return ONLY valid JSON. Say nothing else."

---

## Step 2: Extract All Quotations
**What it does:** Finds all quotations, statements, and testimony from the documents, focusing on witness testimony and excluding court decisions.

**Instructions to AI:** "You are analyzing a collection of documents. Extract all quotations, statements, and testimony from these pages. Focus on witness testimony and personal statements, NOT court decisions or legal rulings.

IMPORTANT:
- Include ALL direct quotations (text in quotation marks or clearly attributed speech).
- Include ALL first-person statements (statements using "I", "we", "my", "our", etc.).
- Include ALL testimony, sworn statements, depositions, or formal declarations.
- EXCLUDE court decisions, legal rulings, judge's opinions, or procedural statements.
- EXCLUDE generic legal language or boilerplate text.
- Focus on personal testimony, witness statements, and direct quotes from people involved.
- Include the speaker's name if mentioned or can be inferred.
- Preserve the exact wording of all quotations and statements.
- If the speaker is unknown, use "Unknown Speaker".
- If a quote seems like a court decision or legal ruling, exclude it.

Return as JSON with these exact keys:
- all_quotations: [quote, speaker]

Return ONLY valid JSON. Say nothing else."

---

## Step 3: Organize by Person
**What it does:** Uses the people names from step 1 and organizes all quotations by person, using standard name spellings.

**Instructions to AI:** "Using the people names extracted earlier and all the quotations found, organize everything by person. For each person mentioned in the documents, compile all their quotes.

IMPORTANT:
- Use the people names from the first step (use the primary/standard spelling).
- Include ALL quotes for each person.
- If a person has no quotes, still include them with an empty quotes array.
- Preserve the exact wording of all quotes.
- Simple format: person name and their quotes.
- If you find quotes attributed to alternative spellings of a name, group them under the primary spelling.
- Focus on witness testimony and personal statements only.
- Exclude any quotes that appear to be court decisions or legal rulings.

Return as JSON with this exact format:
- people_quotations: [person, quotes]

Return ONLY valid JSON. Say nothing else."

---

## Technical Settings
- **Model used:** GPT-4.1 Mini
- **Temperature:** 0.0 (for consistent results)
- **Max tokens:** 1,000,000
- **Timeout:** 120 seconds per step
- **Retry attempts:** 3
- **Retry delay:** 5 seconds 