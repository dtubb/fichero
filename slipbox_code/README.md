# Slipbox - Extract, connect, organize, and cite slip-notes from articles, books, archives, and more using AI

**Version: 2023-12-29**

Slipbox is a command-line tool to help build a slip-box style system for managing notes and sources. 

## Background 

How to keep track of insights researching a topic? How do you organize and interlink your notes, sources, and citations? It is a challenge that knowledge management systems have attempted to address through developing a slip-box or a zettelkasten. 

Sönke Ahrens, a specialist in education and social science, writes in his book []*How to Take Smart Notes*](https://www.soenkeahrens.de/en/takesmartnotes), a how-to guide drawing on the slip-box technique of incredibly prolific German sociologist Niklas Luhmann, considered one of the most important social theorists of the 20th century. What gets Ahrens' attention is less Luhmann’s social theory, but his working method―the slip-box, the zettelkasten. 

Strictly speaking, a slip-box is a box to store notes from readings and references, along with reactions and ideas. For Luhmann it was three sets of index cards stored in wooden boxes. The first set, purely bibliographic, with reference information and a brief description of the content, and on the other side brief notes on the content. The second set, was a collection of notes and ideas on articles. The third set, was a index cards, with keywords, that linked to other notes. 

The process was simple: when he read a piece, Luhman would write both slips—reference and a note about it—on one card. Then he would think about the note's relevance to his own thinking and writing, and then turn to the second slip box, and he would write on one side of an index card one, brief, idea or thought, which he would file in a spot related to other ideas. He would then index that note, in the third set of slip notes.

Slipbox is an open source command line tool, written in Python, that helps facilitate this workflow. It can create slips by extracting key quotes, facts, and insights from articles, books, archives, PDFs, and other sources, including your own reading notes and highlights and annotations of a PDF, using LangChain connected to an AI backend. SlipBox then helps to create a reference note, to tag these slip notes, to connect ideas and themes from disparate sources, and to summarize notes and link them to related slips. Slipbox can link slips together, link them with keywords, and create a slip-box from documents, articles, and books into a flexible slipbox-style system. Generate slips in Markdown, CSV, and JSON format, for importation into other software.

At its core, Slipbox can be given source material and commands to create slips on the most salient points from source materials broadly, to summarize based on a specific query. When used iteratively, Slipbox can work through a folder of documents, to help understand connections between them. Slips can be linked bi-directionally, enabling you to navigate concept pathways and see new contextual relationships. This network of interconnected slip-notes can help kick start a knowledge management system. Later search across the slips using keywords, or follow link trails. By Reading, by feeding the slipbox, and by reviewing the slips, it can help you synthesize ideas at the intersection of concepts.

Slipbox is a command line tool to help generate slips, generate links, generate tags, which can then be best viewed in a different application, like Tinderbox or DevonThink. 

Slipbox runs on your machine, speaks to large language models online or locally, and can help analysis one or a hundred documents.

# How does it work?

Slipbox leverages AI assistants running in a modular "LLM Lab" to help build a slipbox knowledge system from research material.

Key components of the LLM Lab:
- Lab Director Agent: Oversees workflow and assigns tasks to assistants
- Assistant Agents: Modular workers focused on particular tasks
- Validation Assistant: Reviews output quality and suggests improvements
Assistants

User provides sources
- Director assigns tasks to appropriate assistants
- Assistants execute assigned tasks and return output
- Validation assistant reviews output
- Director iterates if needed to improve quality
- Final output is returned to user

If the aim of the Slipbox  is to create a slipbox from research material, it does this leveraging AI assistants running in a modular "LLM Lab" to help build a slipbox knowledge system from research material. It uses AI Agents, running in the cloud or locally, accessed via LangChain. The workflow is as follows. First, the user points the Slipbox terminal application at a folder of documents—PDFs, JPGs (at present), and relartivly easily in the future DOCX, HTML, MD, CVS, EXCEL, and other files. From there, the Slipbox first step is to create a soruce folder, where it will store the original file, the metadata file, and an extract. Additional material, from AI covnersations, about this soruce, will be saved here, as well. Next, the SlipBox app will extract material from the original document. If this is a PDF, of a book, article, etc. the text is genrated, with pages numbers. If the document is a JPG, then the app will use Google Vision to extract the text from the document. From there, the document is passed to the Slipbox "LLM Lab" (sb\_llm\_lab). 

Each lab is modelled conceptually on idea of using Agents and Manbagers to solve a problem  [AgentVerse](https://github.com/openbmb/agentverse#task-solving-showcases). In this case, the SlipBox will ask the Lab to answer a question, for example to review the OCR of a text file. To do this task, the LLM Lab will create various "agents," that take this question, and then choose the next steps.

In this case, a *Lab Director* agent (sb\_llm\_slipbox\_lab\_director) will take the task. It will call on on a Extracted Text Assistabt to review  the the sources. the Lab Director agent will be tasked with u undertaking a task. For example, reviewing the text extracted from a soruce. It will oversea other AI agents, or research assistants, that can work with the source to do a specific task. For example, the first Director will as the Extracts Assistant to review the source text, and knows as much metadata as the slipbox can provide, and then make an educated guess on how to clean up the OCR.

The output will then be sent back to the the Director, whoe will know to send it to a Valaidator Assisant. 

The Validator Assistant will be tasked with reviewing the first Assistant's work. (Ineed, at each step, we'll use a Validator to review the previous assistants work. 

Once the validator is done, the Director will then reach out to a new Assistants whose task is to take the feedback from the validator, considers the first Assistants task, and then to integrate the required changes into the assistnat. This will be sent back to the director, validated one more time, and if it passed, the director will then send it out to an Assistant charged with formating the revised extracted text into the appropriate format for savings to the slipbox folder.

This is just one step. 

It works as follows. A sb_llm_lab_manager class that oversees the lab workflow. The A sb_lab class that initializes the lab environment. A sb_lab_director class that assigns tasks and directs the workflow. A sb_assistant base class that can be subclassed for different tasks

Two initial sb_assistant subclasses:

sb_llm_extracts_assistant - extracts key ideas/quotes from text

sb_llm_validator_assistant - reviews and validates previous output

The general workflow is:

- The user provides the lab with an input question or source text
- The lab director chooses which assistants are needed to process the input
- Assistants execute their tasks and return results
- The director validates the results and iterates if needed
- Final output is returned to the slipbox app to update the slipbox.

It has these assistants at its disposal.

- **Validation/Quality Control Assistant**: Will review the previous prompt and offer an evaluation, critique, suggestions, etc.

- **Extract Review Assistant**: Will review the provided text that is OCR and make suggestions.

**Metadata Extraction Assistants**

- sb_llm_people_assistant - Extracts authors, characters, interviewees
- sb_llm_organizations_assistant - Extracts companies, governments, institutions  
- sb_llm_locations_assistant - Extracts cities, countries, landmarks
- sb_llm_dates_assistant - Extracts dates, eras, time periods
- sb_llm_concepts_assistant - Extracts subjects, theories, ideologies
- sb_llm_events_assistant - Extracts conferences, disasters, events

**SlipBox Reviewer**

- **Summarizing Assistant**: The sb_llm_summarizing_assistant will create a summary of a piece of text.

- **Cataloguing Assistant**: The sb_llm_cataloguing_assistant will create a Dublin Core catalogue for the source, and/or for the entire slipbox.

- The **Slipbox Outline Assistant**: The sb_slipbox_outline_assistant will be able to access the entire context of all the slips.

- The **Tag Outline Assistant**: The sb_slipbox_outline_assistant will be able to access the entire context of all the tags, and return that to the **Slip Tagging Assistant**.

- The **Slip Writer Assistant**: The sb_llm_slip_writer_assistant will review a source, and write a slip based on the source material. A slip is a single note, about a single, atomic idea, in the source. It may include a quote, it may include a summary, discussion, and evaluation of the source, that links it to other slips, references, or tags.

- The **Slip Linking Assistant**: The sb_llm_slip_link_assistant will review a particular slip in the context of all the slips, and suggest linkages to make between one slip and another. 

- The **Slip Tagging Assistant**: The sb_llm_slip_tagging_assistant will review a particular slip in the context of all the tags (keywords), and suggest relevant tags, or create new tag taxonomies.

- The **Slip Organizing Assistant**: The sb_llm_slip_tagging_assistant will review a particular slip in the context of all the slips, provided by the **Slipbox Outline Assistant**, and suggested where the slip can be filed.

- The **Reference Assistant**: Will review the source material, and write an appropriate BibText entry, based on available information.

= The **Formatting Assistants**, which will take the results of the previous assistants, and make sure to return them as JSON, YAML, MARKDOWN, or whatever format is needed.

- The *Question Assistant** - Analyzes slips and proposes questions to ask of the slips, based on interconnected topics, tags, etc.

- The *Insights Assistant* - Identifies novel insights from linking disparate slips. 

- The *Research Assistant** - Analyzes slips and proposes writing prompts or article ideas based on interconnected topics, based on a question.

- *Outline Assistant** - Reviews related slips on a topic and organizes them into a logical outline for drafting an article.

- *Citation Assistant* - Ensures all quotes and ideas are attributed properly with in-text citations.

- *Reference Assistant** - Reviews a text, and makes sure citations are accurate, based on the slipbox. 

- *Review Assistant* - Provides feedback to strengthen arguments, evidence, and flow of a draft, based on material available.

- *Publishing Assistant* - Advises on potential journals, outlets, or publishers to handle submissions, based on what is in the slipbox.

- *Communications Assistant** - Brings together a few slips, and suggests a possible topic to write about.

- The **Future Reading Recommendation Assistabt** - Analyze the conceptual connections between slips and propose related materials for future reading. Trace citations and references to suggest source documents. Identify gaps in the knowledge graph and propose sources to fill them. Compare new sources against existing slips and highlight novel ideas.

- **Concept and Idea Development Assisabt** -Synthesize disparate slips into new conceptual frameworks. Propose research projects based on intersections between slips. Analyze the knowledge graph to identify promising directions for papers. Outline draft papers by selecting and organizing relevant slips. Expand on outlines into full paper drafts.

- sb_llm_insight_assistant - Identifies novel insights
- sb_llm_question_assistant - Proposes questions from slips
- sb_llm_research_assistant - Proposes writing ideas from slips  
- sb_llm_drafting_assistant - Writes drafts based on outlines
- sb_llm_editing_assistant - Refines writing for clarity and flow
- sb_llm_review_assistant - Critiques draft arguments and evidence 
- sb_llm_format_assistant - Handles exporting slips to various formats
- sb_llm_hypothesizer_assistant - Proposes hypotheses
- sb_llm_theorizer_assistant - Formulates theories
- sb_llm_extrapolator_assistant - Extrapolates patterns
- sb_llm_analogizer_assistant - Draws analogies
- sb_llm_metaphorizer_assistant - Creates metaphors
- sb_llm_connector_assistant - Identifies connections between disparate ideas
- sb_llm_analogy_assistant - Draws analogies between concepts
- sb_llm_example_finder_assistant - Finds examples to illustrate ideas
- sb_llm_counterpoint_assistant - Raises counterarguments
- sb_llm_implication_assistant - Determines implications of ideas
- sb_llm_critique_assistant - Constructively critiques arguments
- sb_llm_synthesis_assistant - Synthesizes related ideas into new ones
- sb_llm_metaphor_assistant - Generates explanatory metaphors  
- sb_llm_visualizer_assistant - Creates concept maps and diagrams
- sb_llm_faq_assistant - Generates frequently asked questions
- sb_llm_debate_assistant - Debates ideas dialectically
- sb_llm_devils_advocate_assistant - Raises counterpoints
- sb_llm_inference_assistant - Makes inferences based on evidence
- sb_llm_paradox_finder_assistant - Identifies paradoxes and contradictions

- **The Literature Review Assistant** - Reviews slips on a topic to synthesize a literature review. Suggests additional articles based on gaps.

- **The Research Synthesis Assistant** - Synthesizes key findings, arguments and evidence on a topic into a summary.

- **The Annotated Bibliography Assistant** - Creates an annotated bibliography from sources, organized by theme. 

- **The Reading List Assistant** - Identifies and prioritizes key sources on a topic into a reading list.

- **The Syllabus Assistant** - Structures slips on a topic into a course syllabus.

- **The Journal Recommendation Assistant** - Recommends target journals for a paper draft based on fit and relevance.

- **The Peer Review Assistant** - Provides feedback on a draft's quality and validity based on the slipbox.

- **The Plagiarism Checker Assistant** - Checks draft excerpts against sources to identify potential plagiarism. 

- **The Paraphrasing Assistant** - Rewrites quoted passages while maintaining meaning and citation.

- **The Concept Explanation Assistant** - Explains disciplinary concepts and theories based on the slipbox.

- **The Expert Identification Assistant** - Identifies authors frequently cited on topics as credible experts.

- **The Hypothesis Generation Assistant** - Analyzes observations in slips to propose testable hypotheses.

- **The Interview Synthesis Assistant** - Identifies and synthesizes key themes emerging across interview slips.

# Workflow

1. Director assigns source material to agents
2. Extractor identifies key ideas 
3. Summarizer creates slip notes
4. Linker connects related slips
5. Tagger assigns topics to slips
6. Citer adds citation info  
7. Archiver stores sources

 
Next, the summarizer agent takes the extracts and condenses them into short slip notes - each expressing an atomic idea from the source. The slips are written in Markdown format.

The linker agent then makes connections between related slips, based on their concepts. It links slips on similar topics across sources.

The tagger agent assigns topic tags to each slip, categorizing their subject matter. This structures the emerging knowledge graph.

Meanwhile, the citer agent handles citations, linking slips back to their original sources.

The archiver agent manages the sources folder, ensuring originals are preserved.

Over time, new sources can be added, generating more slips and links. The assistants work together behind the scenes to incrementally build up a web of knowledge.

The professor and students can focus purely on their research, while the AI agents handle extracting ideas from the literature and organizing them into the networked slipbox.

Rather than traditional note taking, the AI assistance facilitates a slipbox knowledge base that can be continually expanded and improved as more sources are added. The modular assistants work 24/7 to build the knowledge graph.

Let me know if this helps explain at a high level how the slipbox lab could benefit professors and students without programming expertise! I'm happy to clarify or elaborate on any part.



# Key Classes

## sb\_llm\_slipbox\_lab\_director

- Oversees agents working with sources to build the slipbox 

## sb\_llm\_slipbox\_agent

- Base class for agents performing slipbox tasks 

# Agents


This allows building a knowledge graph of interconnected slip notes from sources. The modular agents work together under the Director to build and maintain the slipbox.

# Programming Tasks

- Create sb\_llm\_slipbox\_lab\_director class
- Create sb\_llm\_slipbox\_agent base class
- Implement slipbox builder agents
- Integrate into overall slipbox system
- Add workflows to automate slipbox creation  
- Support incremental updates as new sources added

Let me know if this revised focus on the slipbox helps explain the purpose and design better. I'm happy to incorporate additional details or examples.


# Slipbox Folder Structure 

The Slipbox uses a structured folder hierarchy to store the various components of the slip box. This slipbox structure aims to balance human readability with portability across apps: Folder and file naming conventions optimize for understanding at a glance. Numbering scheme enables logical organization and linking. Markdown formatting for plain text readability. Can be easily read (and edited) in any text editor. ID links allow connecting concepts without clutter. The slipbox is designed to work across platforms like: Obsidian, Zettlr, DevonThink, and Tinderbox.

## Overview

```
slipbox/
├── sources/ 
| ├── 1-research-paper/
| | ├── 1-research-paper.pdf  
| | ├── 1-research-paper-source.md 
| | ├── 1-research-paper-extracted.md
| | ├── 1-research-paper-catalog.md
| | └── 1-research-paper-metadata.md
| ├── 2-interview-notes/
| | ├── 2-interview-notes.doc
| | ├── 1-interview-notes-source.md
| | ├── 2-interview-notes-extracted.md
| | ├── 2-interview-notes-catalog.md
| | └── 2-interview-notes-metadata.md
| └── ...
├── slip_notes/  
| ├── 1-zettelkasten.md
| ├── 1-zettelkasten
| | ├── 1a-history.md
| | ├── 1a-history
| | | ├── 1a1-origins.md
| | | └── 1a2-luhmann.md
| | ├── ...
| | ├── 1b-benefits.md
| | └── 1c-examples.md
| | └── 1c-examples
| |   ├── 1c1-analog.md 
| |   └── 1c2-digital.md
| ├── 2-writing.md
| ├── 2-writing
| | ├── 2a-drafting.md
| | └── 2b-editing.md 
| | └── 2b-editing
| |   ├── 2b1-style.md
| |   └── 2b2-grammar.md
| └── 3-python.md
| └── ...
├── refs/
| ├── smith18.bib 
| ├── jones99.bib
| ├── lee2022.bib
| └-─ ...
└── tags/  
| ├── 1-knowledge_management.md
| ├── 1-knowledge_management
| | ├── 1a-tools.md
| | ├── 1a-tools
| | | ├── 1a1-zettelkasten.md
| | | └── 1a2-wikis.md
| | └── 1b-techniques.md
| ├── 2-writing.md
| ├── 2-writing
| | ├── 2a-workflow.md
| | └── 2b-style.md
| └── 3-python.md
└── metadata/
| ├── people/
| | ├── 1-john_smith.md  
| | ├── 2-jane_doe.md
| | └── ...
| ├── places/
| | ├── 1-new_york.md
| | ├── 2-paris.md 
| | └── ...
| └── events/
|   ├── 1-2022-conference_.md
|   ├── 2-2023_symposium.md  
|   └── ...
```

## Sources

The `sources/` folder lies at the foundation of the slipbox, containing the original source material, plus metadata, extracted text, and a GPT generated catalogue file. High-quality sources are essential as the raw material for the slip box. The sources folder serves as an organized archive and staging area for incoming documents. 

Each source is given a folder, named by an incremental number for chronological ordering. 

The `original_file_name` is copied into this folder. It can be a PDF, TXT, or MD file.

Then an `original_file_name-source.md` markdown file is created to store the meta data, original pat.

A `original_file_name-extracted.txt` is generated, for later use summarize and distil into atomic idea units. 

From the extracted file, a GPT will be used to create a Dublin Core `original_file_name-catalog.md`, along with metadata from the file system. The catalog file also inlcudes metadata data for people, organizations, places, events, topics, etc.


Finally, a `original_file_name-metadaa.md` file is created with extrated people, organizations, places, events, topics, keywords, that is corss reverenced to a centralized metadata slips for these entities. 

In this way, the sources folder achieves a clean separation between original source material, a source file, and autmaticalyl generated extracted text file, catalogue file, and metadata file. 

## Slips

The `slips/` folder contains the individual slip notes in Markdown format. Slips can link to each other by ID. The slips folder may also contain subfolders to organize related notes. Slips aim to capture atomic ideas and can cover documents, concepts, theories, summaries, quotations, facts, and other insights.

### Numbering and Structure

- Top level slips like 1-zettelkasten.md cover broad topics
	- Subfolders like 1-zettelkasten/ contain related sub-topics
	- Sub-subfolders like 1a-history/ further divide concepts
- Topics grouped by number, subtopics by letter, granular notes by final number
- Allows both hierarchy through folders and connection across ideas
- Enables linking between slips using the numbering IDs

### Extracted source text is input to the LLM
- The LLM summarizes core ideas into slip notes
- Slips output in Markdown format
- Summarizations and distillations of key concepts
- Quotations, facts, definitions, and insights
- Links to other slips using numbering
- Links to sources using filename references

### Evolution
- Slips can be edited and expanded over time
- New connections to other slips can be made
- Outdated slips re-summarized from sources
- Quality improves through LLM feedback

## References 

The `refs/` folder contains BibTeX (.bib) reference files for each source document. This separates bibliographic metadata from content slips. References handle all source metadata so slips can focus purely on ideas

- References contain bibliographic data like:
	- Title, author, date
	- Publishing info 
	- Page numbers
	- URLs, DOIs
- Updates references without editing slips
- Slips contain ideas without source clutter  
- Enables citing sources without repetitive info
- The refs file lins to source originals in `sources/` folder
- Refs has a link to all its slips.
- Refs has a link to all its tags.
- Integrates with reference managers like Zotero
- One .bib file per source document
- Filenames match source numbering system
- Generated automatically during source import

## Tags

The `tags/` folder contains slip notes defining topics, keywords, and categories that emerge from the knowledge graph. This provides topical structure for classifying slips, where tags represent nodes in the graph of conceptual links, and it enable drilling down concepts from broad to granular.
- The top-level tags cover broad topics, the subfolders contain related sub-topics, and the sub-subfolders further divide concepts.
- Tags arise iteratively over time, as the LLM generates them. It reflects the relationships between slips. New tags can be added as new ideas emerge. 
- Tags link to their slips, and to their referneces. Slips and referneces link to their tags.
- Tag set grows dynamically as more slips created
- Tags can be edited, reorganized, renamed
- Obsolete tags can be deprecated or deleted

The tags folder provides an evolving taxonomy for classifying the emergent knowledge graph. Tag links between slips enable powerful browsing by concept. The organic taxonomy maps contexts and meaning.

## Metadata

The `metadata/` folder contains generated metadata extracted from the sources about people, organizations, locations, dates and etc. extracted through natural language processing. Subfolders may organize different entity types. These contextual slips supplement idea-based slips with real-world references.

People
Organizations
Locations
Dates
Events
Topics

This provided centralized access to these entities, with names, descriptions, relations. The metadata folder structures extracted entities for an overview separate from conceptual slips. It enables consolidated management.


## 
## Usage
```
slipbox.py {pdf_to_text} input [-h] [-o OUTPUT_PATH] [-l LENGTH] [-s SIZE]  
             ...
```

**Positional Arguments:**

Positional arguments specify the command to run. Must be the first argument after slipbox.py.

`{pdf_to_text, summarize}`

- `pdf_to_text`:   Extracts raw text from a PDF file. Splits text from each page into an array. Saves extracted text to output file, with a separator for each page. Currently, page count isn’t accurate if there is no text on a page.

- `summarize`:   Generates a text summary of a PDF file by using a ChatGPT model to summarize the extracted text. Allows customizing summary length with -s/--size.

`{INPUT}`
## Glob Recursive Matching

The `slipbox.py` script supports recursive matching of files and folders using glob patterns. 

To match files recursively under a folder:

```
./path/**/*.{pdf,txt,md}
```

This will match all PDF, text, and Markdown files recursively under "path".

To match folders recursively:

```
./path/**/*/
```

The `**` pattern matches any files or folders recursively under the given path.

Summary:

- Use `**` to recurse into folders to match files/folders
- Match only files with `**/*.{ext1,ext2}`  
- Match only folders with `**/*/`
- Match everything recursively with `**`

**Optional Arguments:** 

`-h, --help`  

- show help message and exit

`-o OUTPUT_PATH, --output-path OUTPUT_PATH`

- Output file or directory. Default is current working directory.  

`-l LENGTH, --length LENGTH`

- **Not Implemented** Number of extracts to generate per source. Default is 5. 

`-s SIZE, --size SIZE` 

- Approximate size of summary in words. Default is 100.

`-v VERBOSITY, --verbose VERBOSITY` 

- Debug level. Controls the level of debug messages printed. Higher values print more verbose debug output during execution. This helps troubleshoot issues without overhead in regular usage. Default is “NONE” for clean output. Set to DEBUG when developing or debugging new functionality. Options are:

  - 0/NONE - No debug messages
  - 1/INFO - Print standard informational messages
  - 2/ERROR - Print errors only

You're absolutely right, my values for the log level options were incorrect. Here is an updated Logging section with the correct log level values:

`-l LOG_LEVEL, --loglevel LOG_LEVEL`

- Log level output diagnostic messages. The log level can be configured to determine the level of detail in the logs. By default, the log level is set to 'NONE'. You can customize the log level when running Slipbox. Log file is “slipbox.log”.


The `--loglevel`/`-l` argument allows setting the log level. The logging level determines the amount of detail included in logs. Logs will be recorded for all items at or below the chosen level.

```
slipbox.py inputs command --loglevel LOG_LEVEL
```

Log levels (ordered from most to least severe):

0/NONE - No logs kept
1/FATAL - Fatal error messages
2/CRITICAL - Critical messages
3/ERROR - Error messages
4/WARNING - Warning messages
5/INFO - Informational messages
6/DEBUG - Debug messages

For example:

```
slipbox extract file.txt --loglevel INFO
```
Would log messages for INFO, WARNING, ERROR, CRITICAL and FATAL levels.

Logging helps troubleshoot issues without overhead during regular use. The default log level is NONE.

`-d DEBUG_LEVEL, --debug DEBUG_LEVEL`

- Denbug level will disable access to network and GPT requests. The debug levelk can be configured to determine the level of debugging. By default, the debug level is set to 'INACTIVE'. You can customize the debug level when running Slipbox:

The `--debug`/`-d` argument allows setting the debug level:

- 0/INACTIVE - No debugging. All functions accesed.
- 1/ACTIVE - Debugging enabled. All GPT and File access disabled.

```
slipbox.py inputs command --debug LEVEL
```

This will disable access to the GPT and aid in troubleshooting. 

**Examples**:

Extract text from a PDF:

```bash
$ slipbox.py paper.pdf pdf_to_text -o text/
```

This will extract text from paper.pdf and save it to text/paper.txt

Summarize a PDF to 100 words
```bash
$slipbox.py paper.pdf summarize
```

Summarize to a custom size 

```bash
slipbox.py paper.pdf summarize -s 50
```

## Current Features

- Extract text from PDF documents
- Save extracted text to file or directory  

## Roadmap

Planned features:

- Extract quotes and key points from plain text
- Generate summaries from extracted text 
- Automatically tag extracted points
- Link between extracted points
- Output slips in various formats (Markdown, CSV, JSON)

```bash
python slipbox.py book.txt extract
python slipbox.py extracts.txt summarize
```

## Contributing

Check out the project on GitHub to get started and help improve Slipbox. Contributions are welcome!