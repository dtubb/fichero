# How the Document Cataloguing System Works

## Overview
This system automatically analyzes historical documents and creates detailed catalogues with key information extracted from the text. Think of it as a smart assistant that reads through your documents and creates organized summaries.

## What It Does (Step by Step)

### 1. **People, Organizations & Places**
The system first looks for and identifies:
- **People**: Names, titles, roles mentioned in the documents
- **Organizations**: Companies, institutions, government agencies
- **Locations**: Cities, states, countries, addresses

*Example: If a document mentions "John Smith, manager of ABC Mining Company in Denver, Colorado" - it will extract John Smith (person), ABC Mining Company (organization), and Denver, Colorado (location).*

### 2. **Dates, Legal References & Rivers**
Next, it finds:
- **Dates**: Specific dates, years, time periods mentioned
- **Legal References**: Case numbers, laws, regulations
- **Rivers**: Waterways, tributaries, bodies of water

*Example: "On March 15, 1923, according to Case #12345, the Colorado River..." would extract the date, case number, and river name.*

### 3. **Specialized Information**
The system then looks for specific types of information common in historical documents:
- **Key Events**: Important meetings, incidents, transactions
- **Mines**: Mining claims, shaft names, mining operations
- **Properties**: Land parcels, buildings, estates
- **Equipment**: Dredges, machinery, tools
- **Animals & Plants**: Livestock, crops, notable specimens
- **Weapons**: Firearms, equipment mentioned
- **Injuries**: Medical conditions, accidents, health issues

### 4. **Timeline Creation**
Using all the dates and events found, the system creates a chronological timeline of important events in the documents.

### 5. **Key People & Tags**
The system identifies:
- The 5-10 most important people mentioned
- 5-10 descriptive tags that capture the main themes (like "mining dispute," "property rights," "legal case")

### 6. **Summary**
Finally, it creates a 150-word summary that gives you a clear overview of what the documents are about, suitable for archival records.

## What You Get

After processing, you'll receive:
1. **Detailed catalogues** with all the extracted information organized by category
2. **Word documents** with the original images and transcriptions side-by-side
3. **Structured data** that can be easily searched and referenced

## How to Use It

1. **Prepare your documents**: Scan or photograph your historical documents
2. **Choose the English workflow**: Select "Transcribe and Catalogue (English)" 
3. **Run the process**: The system will automatically process all documents
4. **Review results**: Check the generated catalogues and Word documents

## Benefits

- **Saves time**: No need to manually read through hundreds of pages
- **Consistent**: Uses the same analysis method for all documents
- **Searchable**: Creates structured data you can easily search
- **Archival quality**: Produces professional catalogues suitable for archives
- **Comprehensive**: Captures details you might miss during manual review

## Technical Notes (For Reference)

The system uses advanced AI models (GPT-4.1 Mini and GPT-4.1) to:
- Read and understand document content
- Identify patterns and relationships
- Generate structured data in JSON format
- Create human-readable summaries

All processing is done locally or through secure API connections, ensuring your documents remain private and secure. 