import typer
import spacy
from lxml import etree
from pathlib import Path
import json
from rich.progress import Progress

app = typer.Typer()

# Load spaCy model
nlp = spacy.load("es_core_news_lg")

def process_xml(xml_file: Path, force_update: bool = False) -> None:
    """
    Process an XML file to extract named entities and update the XML file.

    :param xml_file: Path to the XML file
    :param force_update: Force update even if data exists
    """

    # Check if the XML file has already been processed
    ner_json_file = xml_file.with_suffix(".ner.json")
    if ner_json_file.exists() and not force_update:
        # Check if the ner.json file is empty
        if ner_json_file.stat().st_size == 0:
            # If the ner.json file is empty, process the XML file
            pass
        else:
            # If the ner.json file is not empty, skip the file
            return

    try:
        # Load XML with recovery option
        parser = etree.XMLParser(recover=True)
        tree = etree.parse(xml_file, parser)
    except Exception as e:
        print(f"Error parsing {xml_file.name}: {e}")
        return

    # Define the namespace
    ns = {'alto': 'http://www.loc.gov/standards/alto/ns-v4#'}

    # Find Page element
    page_elem = tree.find(".//{http://www.loc.gov/standards/alto/ns-v4#}Page")

    if page_elem is None:
        print(f"No Page element found in {xml_file.name}")
        return

    # Get the String element under the Page element
    string_elem = page_elem.find("{http://www.loc.gov/standards/alto/ns-v4#}String")

    if string_elem is None:
        print(f"No String element found under Page in {xml_file.name}")
        # Create an empty ner.json file
        try:
            with open(ner_json_file, "w", encoding="utf-8") as f:
                json.dump({}, f)
        except Exception as e:
            print(f"Error writing {ner_json_file.name}: {e}")
        return

    # Get the full text from the String element
    full_text = string_elem.get("CONTENT", "")

    """
    ======================================
    LOAD OR CREATE Entities from Full_Text using spaCy
    ========================
    """
    # Define the entity categories
    entity_categories = ["PER", "LOC", "ORG", "DATE", "MISC"]

    # Initialize the entities dictionary with lists for each category
    entities = {category: [] for category in entity_categories}

    # Remove existing Entity elements from the XML
    for entity_elem in tree.findall(".//{http://www.loc.gov/standards/alto/ns-v4#}Entity", namespaces=ns):
        entity_elem.getparent().remove(entity_elem)

    # Extract named entities using spaCy
    spacy_doc = nlp(full_text)

    # Iterate over the extracted entities and populate the entities dictionary
    for ent in spacy_doc.ents:
        entity_data = {
            "text": ent.text,
            "start": ent.start_char,
            "end": ent.end_char,
            "label": ent.label_
        }
        if ent.label_ in entity_categories:
            entities[ent.label_].append(entity_data)
        else:
            entities["MISC"].append(entity_data)

    # Create XML elements for each entity and append to Page element
    for category, entity_list in entities.items():
        for entity in entity_list:
            entity_elem = etree.Element("{http://www.loc.gov/standards/alto/ns-v4#}Entity", nsmap=ns)
            entity_elem.set("type", category)
            entity_elem.set("start", str(entity["start"]))
            entity_elem.set("end", str(entity["end"]))
            entity_elem.text = entity["text"]
            page_elem.append(entity_elem)

    # Save the modified XML
    try:
        tree.write(xml_file, pretty_print=True, encoding="utf-8", xml_declaration=True)
    except Exception as e:
        print(f"Error writing {xml_file.name}: {e}")
        return

    # Save named entities to a JSON file
    try:
        with open(ner_json_file, "w", encoding="utf-8") as f:
            json.dump(entities, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error writing {ner_json_file.name}: {e}")
        return

@app.command()
def main(
    path: Path = typer.Argument(..., help="Path to the XML file or directory"),
    force_update: bool = typer.Option(False, "--force", "-f", help="Force update even if data exists"),
):
    """
    Process an XML file or a directory of XML files to extract named entities and update the XML files.
    """

    if path.is_dir():
        xml_files = list(path.rglob("*.xml"))
    else:
        xml_files = [path]

    total_files = len(xml_files)
    print(f"Processing {total_files} files...")

    with Progress() as progress:
        task = progress.add_task("[green]Processing...", total=total_files)
        skipped_files_count = 0
        processed_files_count = 0

        for xml_file in xml_files:
            ner_json_file = xml_file.with_suffix(".ner.json")
            if ner_json_file.exists() and not force_update:
                skipped_files_count += 1
                continue

            process_xml(xml_file, force_update)
            processed_files_count += 1
            progress.update(task, advance=1)

        if skipped_files_count > 0:
            print(f"{skipped_files_count} files were skipped.")

    print(f"Processed {processed_files_count} files.")

if __name__ == "__main__":
    app()