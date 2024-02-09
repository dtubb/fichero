**Building a *Fichero*: New Tools, Old Documents, and Machine Learning Workflows with an Andangered Afro-Colombian Archive**

Andrew Paul Janco^[Andrew Paul Janco, UPenn Digital Libraries, apjanco@upenn.edu], Daniel Tubb^[Daniel Tubb, Anthropology, UNB Fredericton]

How can machine learning pipelines help catalogue an endangered archive for community researchers, students, historians, and others? Until 2022, the Istmina Circuit Court archive, with documents from the 1870s to 1930s, was rotting, disorganized, and exposed to the elements in garbage bags. Yet, this archive is a crucial source of Afro-Colombian history, in a region too often forgotten in Colombian historiography. In 2023, five young archivists from Istmina and the departmental capital Quibdó worked with the Muntu Bantu Center for Afro-diasporic studies and researchers from UPenn, the University of New Brunswick, and the University of Michigan, with funding from the British Library and the Canadian Social Sciences and Humanities Research Council, to clean, store, and digitize the archive, which is now available online.[^1] While the students catalogued 330 Case Files and wrote a book of micro-history,[^2] the task of cataloguing 470 more cases remains, each has hundreds of damaged documents. In this paper, we reflect on a machine learning pipelines to extract text and catalogue the archive, using Weasel,[^3] a workflow system. to understand 61,000 images"

To extract text, we built a Weasel workflow that (1) fetches images from the British Library; (2) uses Kraken to segment text in each image;[^6] (3) deploys Google Vision to extract handwritten or typewritten text;[^5] (4) sends the image, the polygonal representations, and text to Escriptorium, where users can review it and correct the text.[^4] Here, we discuss successes and challenges in recognizing text in typewritten versus handwritten documents, in segmenting images into regions. 

To create a catalogue, we built a Weasel workflow that (1) downloads transcriptions from eScriptorium, (2) uses sPacy named entity recognition to extract and link the names of people, places, dates, events, organizations;[^4] (3) employs open-source large-language models running locally via Ollama (mistral:instruct and mistral:8x7b) to generate summaries, timelines, catalogue entries, and other catalogue material;[^8] (7) experiments with Ratatouille, Colbert, LangGraph, and agent-based workflows to understand the archive further;[^10] (8) exports this material as a Markdown catalogue of extracted text, summaries, named entities, keywords, etc into a *fichero*, a box of linked and tagged digital index cards which Obsidian and similar tools make accessible to non-technical users; (9) leverages Nomic's Atlas to map the metadata; and finally (10) deploys Jeckyll[^9] to built a static website of the catalogue. We discuss steps to create a machine-generated catalogue, challenges to choose the right approaches, the costs of online commercial AI models, and the importance of the right tool.
 
In conclusion, we consider the importance of training researchers, of community ownership, and of open source tools, and the  spectre of further enclosure of archival materials. Just as tech giants in the AI sector are enclosing the open-Web, we fear these tools could allow a similar enclosure of the past. Nevertheless, we remain optimistic that open-source machine learning workflows can allow for new interpretations of old documents in ways that help people recover otherwise erased histories.

[^1]: See https://eap.bl.uk/project/EAP1477).

[^2]: Taborda Castañeda, Nallely, Ernestina Lemos Rentería, Javier Hurtado Ibargüen, Jhon Leison Rivas Rodríguez, and Yusleyda Perea Cuesta. *Memorias Vivas de Un Achivo Muerto: Archivo Histórico Del Juzgado Del Circuito de Istmina, 1860-1930.* Quibdoi: Semillero Recuperación de Archivos en Peligro / Muntú Bantú, Fundación Social Afrocolombíana Centro de Memoria, Documentación, y Materialidades Afrodíaspóricas, 2023.

[^3]: Explosion. "Weasel: A small and easy workflow system," *GitHub*, https://github.com/explosion/weasel. Accessed February 9, 2024."

[^4]: Escriptorium is a project to help provide digital recognition of handwritten documents using machine learning. "eScriptorium." Sofer Stam, https://gitlab.com/scripta/escriptorium/. Accessed February 9, 2024.

[^5]: Google. "Google Vision AI." Google Cloud, https://cloud.google.com/vision. Accessed February 9, 2024.

[^6]: kraken is a turn-key OCR system optimized for historical and non-Latin script material. See mittagessen. "Kraken." GitHub, https://github.com/mittagessen/kraken/tree/main. Accessed February 9, 2024.

[^7]: spaCy is a Natural Language Processing tool, see  Explosion. "spaCy." Explosion, https://spacy.io/. Accessed February 9, 2024.

[^8]: Ollama is a tool to run LLMs locally.

[^9]: https://jekyllrb.com

[^10]: 
