# TODO

## Next Task
- Add GPT logic to sb_lab
- Implement Director, Extractor, and  Valdiator logic


## Next Tasks

- [X] Generate proper source ID and folder name in add_source()
- [X] Create source folder if it doesn't exist
- [ ]  Extract text and metadata after import
- [ ]  Save extracted text and metadata to files
- [ ]  Load extracted data into Source object
- [ ]  Handle errors/exceptions during import
- [ ]  Validate imported file type and info
- [ ]  Test importing multiple source files
 
- [/] File processor module
  - [ ] Extract text
  - [ ] Extract metadata
  - [ ] Construct ImportFile objects
  
## Next Tasks  

- [ ] Implement per-file processing
  - [ ] Pass files to processor 
  - [ ] Extract text
  - [ ] Extract metadata
  - [ ] Generate ImportFile objects
  - [ ] Handle errors/logging
  
- [ ] Add validation
  - [ ] Validate allowed extensions
  - [ ] Validate input files exist
  - [ ] Validate output dir exists

- [ ] Logging
	- [X] Create sb\_logging.py module
	- [X] Define log levels and message format
	- [X] Set up basic logging config
	- [X] Handle logging configuration from CLI
	- [X] Export logger to import in modules
	- [X] Import the logging module
	- [X] Define a log file path
	- [X] Set a log\_file\_path variable to specify the output file
	- [X] Initialize the logger
	- [X] Create a logger object
	- [X] Configure it to log to the defined file path
	- [X] Set the log file format
	- [X] Define log level mappings
	- [X] Log level integers to logging Level objects (DEBUG, INFO etc)
	- [X] Update the log() function
	- [X] Have log() call the appropriate logger method instead of printing
	- [X] Pass the message and log level
	- [ ] Log PDF loading in sb\_pdf\_to\_text
	- [ ] Add log rotation handling
	- [ ] Configure log rotation to avoid one huge file	 
	- [ ] Set the log file format
	- [ ] Handle logging on program exit
	- [ ] Ensure any buffered logs are written on exit
	- [ ] Consider alternative log levels
	- [ ] May want different levels than just numeric values
	- [ ] Add logger configuration
	- [ ] Allow configuring file path, level via arguments

- [X] Debug Mode
	- [X] Add --debug flag to argparse
	- [x] Add --debug-type argument
	- [ ] Create DebugConfig class
	- [ ] Stub out PyPDFLoader for unit tests
	- [ ] Mock API responses 
	- [ ] Mock CLI input in debug mode
	- [ ] Conditionally load real/stub modules

- [ ] Google Vision
	- [ ] Integrate Google Cloud Vision API
	- [ ] Extract metadata from JPEG
	- [ ] Recognize text/objects
	- [ ] Add CLI argument for vision command
	- [ ] Implement vision module

- [ ] Refactor File Handling
	- [ ] Abstract output path functions
	- [ ] Validate multiple file inputs
	- [ ] Loop through files and process
	- [ ] Support input directories
	- [ ] Recursively search sub-folders

- [ ] Refactor file output handling
	- [ ] Abstract output path logic to utils
	- [ ] Add ability to work on multiple files, directories, and recursively.

- [ ] Handle Multiple Inputs
	- [ ] Update argparse to allow multiple file inputs
	- [ ] Validate each input file exists
	- [ ] Loop through args.inputs and process each file

	- [ ] Support Folders as Input
		- [ ] Check if input arg is a folder with os.path.isdir()
		- [ ] Get list of files with os.listdir()
		- [ ] Loop through and process each file

	- [ ] Recursive Folder Input
		- [ ] Use os.walk() to walk folder tree recursively
		- [ ] Process files, skip folders
	
	
- [ ] Add `catalogue` as new positional command in `slipbox.py`
	- [ ] Develop prompt template for extracting Dublin Core fields
	- [ ] Template needs placeholders for source material and extracted fields
	- [ ] Implement Dublin Core extraction logic
	- Extract key fields like title, creator, date, etc from source
	- [ ] Write XML output to file(s)

## Future General 

- [ ] Add standard output
- [ ] Improve CLI output and messages
- [ ] Add logging for better debuggability 
- [ ] Write docs for modules and functions

## Future Features
- [ ] Extract key points from plain text
- [ ] Auto tag extracted points
- [ ] Implement linking between extracts
- [ ] Additional output formats:
	- [ ] Markdown
	- [ ] CSV
	- [ ] JSON

# Completed Tasks

## 2023-12-28
- [X] Make overview of slipbox folder structure and file conventions
- [X] Define classes in CLASS DESCRIPTIONS
	- [X] Add src/sb\_slipbox.py: Main SlipBox class to initialize and manage system
		- [X] Add src/sb\_slipbox\_manager.py: Top level manager for other managers	
			- [X] Add src/sb\_managers/: Folder containing manager classes
			- [X] src/sb\_managers/sb\_sources\_manager.py: Manages source documents
			- [X] rc/sb\_managers/sb\_extracts\_manager.py: Manages extracts 
			- [X] src/sb\_managers/sb\_slips\_manager.py: Manages slips
			- [X] src/sb\_managers/sb\_tags\_manager.py: Manages tags
			- [X] src/sb\_sources/: Folder for source classes
			- [X] src/sb\_sources/sb\_source.py: Class representing a source

- [X] Implemented sb\_sources\_manager to load sources
	- [X] Initializes folder, if needed
	- [X] Creates Source objects
	- [X] Iterates contents to find valid sources
	- [X] Logs and validates result

## 2023-12-26
- [X] Refactor file handling into modules
  - [X] Create file\_importer module
  - [X] Create file\_crawler module
  - [X] Create file\_processor module (scaffolding only)

- [X] Allow passing allowed extensions as argument
  - [X] Update slipbox.py with --extensions
  - [X] Pass extensions to file importer/crawler
  - [X] Filter files by extension in crawler

## 2023-12-24
- [X] Refactor imports
	- [X]  Create init.py in slipbox package
	- [X]  Export common imports from modules
	- [X] (e.g. from .sb_verbose import * as verbose)
	- [X]  Allow importing shared items with prefixes
	- [X] (e.g. from slipbox import verbose, log, debug)

- [X] TODO: Constants module
	- [X] Create constants.py  
	- [x] Import needed constants from sb\_verbose and sb_log
	- [X]Define Enums for VerbosityLevels and LogLevels
	- [X] Export constants
	- [X] This would define the central location for constants.

- [X] TODO: Define Enums
	- [X] Define VerbosityLevels Enum  
	- [X] Add members NONE, ERROR, INFO etc
	- [X]Assign increasing integer values

- [X] Define LogLevels Enum
	- [X] Add members like PROCESS, IO etc
	- [X] Assign increasing integer values
	- [X] Export Enums from constants
	- [X] Make available to import in other modules
	
## 2023-12-23
- [X] Add verbosity for debugging and errors

## 2023-12-21
- [X] Implement text summarization module
	- [X] Add sb_summarize.py 
	- [X] Integrate with argparse
	- [X] Generate summary from extracted text

## 2023-12-20
- [x] Create initial project scaffolding and folder structure
- [x] Add argparse for command line arguments
- [x] Add main slipbox.py entry point
- [x] Implement PDF to text extraction command 
- [x] Add sb\_pdf\_to\_text module
- [x] Use PyPDFLoader for PDF loading and extraction
- [x] Output extracted text to file/directory
- [x] Support file path or directory for output
- [x] Default to current directory if no output specified
- [x] Add README documentation
- [x] Set up changelog tracking
