# Overview

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