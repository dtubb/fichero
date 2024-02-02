PROMPT:
You are an AI expert at NER and cataloguing archival materials. Review the attached source document, and then fill out the attached template with as much information as you can. If you cannot fill out information, leave it blank. Do not make anything up. Return the result as a Markdown code block with metadata in YAML at the start as in the template. Say nothing else. Return result in the language of the source document.

TEMPLATE:
```
{document_template.md}
```
SOURCE:
{source.txt}