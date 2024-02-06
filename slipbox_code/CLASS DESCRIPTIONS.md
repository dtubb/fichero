# Class Architecture

## Slipbox

The Slipbox class handles overall coordination of the system and slipbox lifecycle.

- Initializes slipbox directory and configuration settings
- Coordinates managers and components
- Persists slipbox data to files/database
- Provides simplified client interface

## SlipboxManager 

Top-level manager that coordinates domain-specific managers. Controlled by Slipbox class.

- **SourceManager** - Manages digital source documents
- **ReferenceManager** - Manages reference data
- **SlipNoteManager** - Manages atomic knowledge note slips
- **TagNoteManager** - Manages topic and keyword tag slips
- **ExtractedMetadataManager** - Manages metadata extracted from sources

## SourceManager

Manages digital source documents added to the slipbox.

- **Source** - Represents an original source document
  - **OriginalFile** - The uploaded source file
  - **ExtractedText** - Plain text extracted from source
  - **CatalogData** - Metadata catalog about the source
  - **ExtractedMetadata** - Structured metadata extracted from source
    - **MetadataType1** - Specific metadata type class 
    - **MetadataType2** - Specific metadata type class

## ReferenceManager

Manages bibliographic reference data.

- **Reference** - Represents a bibliographic reference entry

## SlipNoteManager

Manages atomic knowledge note slips.

- **SlipNote** - Represents an individual knowledge note slip

## TagNoteManager

Manages topic and keyword tag slips. 

- **TagNote** - Represents a topic or keyword tag slip

## ExtractedMetadataManager

Manages metadata extracted from source documents.

- **ExtractedMetadata** - Base class for extracted metadata
  - **MetadataType1** - Domain-specific metadata type
  - **MetadataType2** - Domain-specific metadata type