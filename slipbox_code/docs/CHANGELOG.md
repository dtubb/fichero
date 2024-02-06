# Changelog

# 2024-01-16
  - Implement langraph worklfpw fpr the sb\_lab, and got rid of the sb\_lab director. the sb\_lab its own assistat tools it can access, implemented through the langgraph
  
- Implemented langraph workflow in sb\_lab\_agent base class, so that the assistants can have their own langrpahs if required.
  - Added methods for graph creation, compilation, and destruction
  - Assistants will have their own graph capabilities

- Created ocr\_cleanup tool and assistant
  - Assistant defines ocr\_cleanup() method
  - Registers as langraph node
  - Crafts prompt to invoke tool

## Next Tasks

- Finalize ocr_cleanup() logic in assistant
  - Implement nodes, workflow, and entry point, and conditional\_entry

- Add validator assistant_tool_ 
  - Reviews ocr_cleanup() output
  - Suggests improvements
  
- Connect validator to workflow
  - Add validator nodes and edges
  - Iteratively improve output
  
- Test end-to-end workflow with sample docs
- Then hook it up to the extractor

2024-01-12
- Refactored sb_lab to integrate LangGraph workflow
- Plan is: to use LangGraph at the (sb\_lab level) and at the agent level.
2024-01-05

### Added
- This week,  planned the Lab architecture to do all the work. It’s described in the Readme. 
- Labs can be created to handle slipbox tasks
- Added sb\_\lab and sb\_\lab\_manager classes
	- Created lab director, assistant, and validator agents
- Workflows assign tasks to appropriate agents
- Updated slipbox to initialize sb\_lab\_manager
- Implement agent logic to connect to LangChain and the GPTs
- Implement the Director, validator, and OCR agents.

## 2023-12-31

### Added
- Implemented Google Vision for JPGs.
	- Works really well on typed documents, especially when I manually test. Far better then Abbey Fine Reader.

## 2023-12-30

### Added
- Implemented PDF to Text

## 2023-12-29

### Added

- Implemented sb\_sources\_manager add\_source(self, file\_path) method to import sources
  - - Added import\_files() method to import list of files
    - Validates paths
    - Calls add\_source() for each path  
    - Creates new sb\_source instance
  - Appends instance to sources
  - Calls import\_source\_file()
  - Added import\_source\_file() to sb\_source
    - Creates a folder, calcualtes properties
    - Copies source file to folder
    - Renames file with ID prefix

### Changed
- Updated slipbox.py to call import\_files()
 
## 2023-12-28

### Added
- README.md: Added overview of slipbox folder structure and file conventions and explained purpose and contents of each folder, as well as the naming of the slips and tags folder. 1.a.
- Worked out the classes in CLASS DESCRIPTIONS
	- src/sb\_slipbox.py: Main SlipBox class to initialize and manage system
		- src/sb\_slipbox\_manager.py: Top level manager for other managers	
			- src/sb\_managers/: Folder containing manager classes
			- src/sb\_managers/sb\_sources\_manager.py: Manages source documents
			- src/sb\_managers/sb\_extracts\_manager.py: Manages extracts 
			- src/sb\_managers/sb\_slips\_manager.py: Manages slips
			- src/sb\_managers/sb\_tags\_manager.py: Manages tags
			- src/sb\_sources/: Folder for source classes
			- src/sb\_sources/sb\_source.py: Class representing a source

- Implemented sb\_sources\_manager to load sources
	- Initializes folder, if needed
	- Creates Source objects
		- Iterates contents to find valid sources
	- Logs and validates result

- Added import\_source\_file() method to Source class
- Copies original source file into source folder
- Updated add\_source() method to create Source without loading
- Call import\_source\_file() from add\_source() to import file
- Source file now copied to folder on add, but extracts and metadata not yet generated

Next steps:
- Process imported files	

### Changed
- Added log\_and\_print() function
	- Logs message to file and prints to console
	- Handles both logging and verbosity in one call
	- Reduces duplicated log/print statements

## 2023-12-26

### Added
- File importer module
	- Initializes crawler and processor
	- Handles expanding glob patterns
	- Passes allowed extensions to crawler
	- Has default file extensions, defined in the constant.py file
	
- File crawler module
	- Filters discovered files by allowed extensions
	- Logs allowed extensions
	
- File processor module (scaffolding only)
	- Will handle per-file processing
	
### Changed

- Updated file\_importer to pass allowed extensions to crawler
- Updated file\_crawler to filter files by extension
- Added logging of allowed extensions

### Fixed

- NA

## 2023.12-24

### Changed

Today, I refactored the sb\_log and sb\_verbose to use enums, I added sb\_debug, I changed the folder structure, I refactored the folder structure, and I added the logger so that the log file works.

- Reduced number of debugs, and verbosity levels to 2:	 NONE, INFO, ERROR. For Logger, I matched it to the logger level.


## 2023.12-24

### Changed

Today, I refactored the sb\_log and sb\_verbose to use enums, I added sb\_debug, I changed the folder structure, I refactored the folder structure, and I added the logger so that the log file works.

- Reduced number of debugs, and verbosity levels to 2:	 NONE, INFO, ERROR. For Logger, I matched it to the logger level.

- Created global logger instance
- Added level configuration functions
- Improved log message formatting

- Package Structure and Imports
	- Refactored project into proper packages 
	- Added empty `\_\_init\_\_.py` files to `src` and `src/common` folders
	- This initializes them as packages and allows submodules to be imported
	- Changed imports to use package namespace 
	- Imports are now from the root `src` package rather than flat files
	- e.g. `from src.common import *`

	- Standardized import order and groupings
	 - Moved imports to top of files
	 	- Grouped stdlib, third-party, local imports

- Refactored logging and verbosity to use ENUMs 
	- Moved ENUM definitions to sb\_constants.py
	- Logging and verbosity levels are now ENUM members rather than raw integers
	- Configured levels and set globals to ENUM members rather than integers
	- Removed direct integer comparisons and replaced with ENUM comparisons
	- Improved type safety by enforcing levels are ENUM types rather than loose integers
	- Centralized level configuration and validation based on defined ENUMs
	- Benefits cleanliness of code by removing raw integers in favor of explicit levels
	- This change standardized the representation of levels as ENUMs rather than loose integers. It centralizes configuration based on defined constants and improves type safety.
	- Commented verbosity and log code.
	
I also added a debugging module

- Added sb\_debug.py module to enable debugging.
	- Debugging is now configured through -d/--debug flag
	- Debug levels are defined as enums in sb\_constants.py (Active nad Inactive)
	- get\_debug\_level(), set\_debug\_level() added for handling state
	- is\_debugging() helper added to check debugging status

- Of note, logigng is not used yet, and debugging needs to be enabled in the moduels.

## 2023.12-23 

Today I added a -v/--verbosity mode for debugging. I setup a sb\_verbose module to export verbose functionality. Modules can now simply call the verbose\_print() method rather than handling prints separately. I added a command line arguments to set the vervosity control.

### Added

- Logging
	- Added structured logging module sb\_log
	- Logs are now handled through a consistent logging API
	- Supported log levels matching Niklas Luhmann's levels:
	- PROCESS, IO, API, EXTRACT, SUMMARY, CONFIG, USER, VALIDATION, ERROR, CRITICAL, NONE
	- Log messages are filtered based on the configured log level
	- Default level is ERROR
	- Added -l/--log-level argument to configure level
	- Example:

	```bash	
	slipbox test.pdf pdf\_to\_text --log-level EXTRACT
	```
	


- Verbosity Control
	- Added support for configurable verbosity levels to control debug output:
	- Added `-v`/`--verbosity` argument to slipbox.py to set level
	- Accepts values 0-5, DEBUG (5), DETAILED(4), INFO(3), WARNING(2), ERROR(1), NONE(0), default NONE.
	- sb\_verbose.configure\_verbosity() validates value and sets level
	- Example:
	
	```
	slipbox test.pdf pdf\_to\_text -v ERROR
	```
	
	- This will only print messages logged at the ERROR level or above.
	- The verbosity functionality allows:
	- Controlling amount of debug output
	- Centralized handling of level configuration
	- Consistent logging format
	- This provides debug capabilities without runtime overhead during normal use.
	
### Changed

- Updated modules to check verbosity level
	- Wrapped verbose output in verbosity level checks
	- Prints more info on higher verbosity


## 2023.12.21

### Added

- Implemented PDF summarization module
	- Added sb\_summarize.py module
	- Integrated with argparse for --size argument
	- Generates summary from extracted PDF text
	- Constructs prompt template incrementally
	- Uses f-strings to format size in prompt
	- Avoids premature formatting of {pages} placeholder 
	- Loads pages before constructing full template
	- Outputs summaries to file
	- Example
	
	```bash
	python slipbox.py paper.pdf summarize -s 100 -o summary.txt
	```


### Changed 
- n/a - nothing changed

### Fixed
- n/a - nothing broken

## 2023.12.20

### Added

- Created initial project scaffolding and folder structure
- Added argparse for command line arguments
	- Options for input, output, commands
- Added main slipbox.py entry point
	- Checks args and calls function for command
	
- Implemented “pdf\_to\_text” command for text extraction using PyPDFLoader
	- Added sb\_pdf\_to\_text.py module
	- Uses PyPDFLoader to extract text
	- Saves text output to file or directory
	- Handles output path as file or dir
	- Defaults to current directory and pdf.txt filename
	- Usage:
	
	```bash	
	slipbox.py paper.pdf pdf\_to\_text # Saves to current dir as paper.txt
	slipbox.py paper.pdf pdf\_to\_text -o text/ # Saves as text/paper.txt
	```

- Added documentation to READ ME.
- Updated the Changelog.

### Changed 
- n/a - first day of development

### Fixed
- n/a - first day of development

### Next
- Implement text summarization
	- Add sb\_summarize.py module
	- Integrate with argparse
	- Generate summary from extracted text
	
- Refactor file output handling
	- Abstract output path logic from sb\_pdf\_to\_text into separate util function
	- Handle saving file to output dir or file path	
	- Default to current dir if none specified
	- Utilities for generating output filename from input

## 2023.12.19

- Drafted [readme.md.](./readme.md)