import typer
import spacy
import srsly 
from lxml import etree
from pathlib import Path
import json
from rich.progress import track
from typing_extensions import Annotated
from simple_alto_parser import AltoFileParser

app = typer.Typer()

def get_page_fulltext(xml_tree):
    # assert that the XML file is an ALTO file
    if xml_tree.getroot().tag != "{http://www.loc.gov/standards/alto/ns-v4#}alto":
        raise ValueError(f"{xml_file} is not an ALTO file")
    # xmlns from xml_tree
    xmlns = xml_tree.getroot().nsmap[None]
    
    # from: https://github.com/RISE-UNIBAS/simple-alto-parser
    page_content = """"""
    for text_block in xml_tree.iterfind('.//{%s}TextBlock' % xmlns):
        block_content = ""
        for text_line in text_block.iterfind('.//{%s}TextLine' % xmlns):
            line_content = ""
            for text_bit in text_line.findall('{%s}String' % xmlns):
                bit_content = text_bit.attrib.get('CONTENT')
                line_content += " " + bit_content

            block_content += line_content
        page_content += block_content + "\n"

    return page_content

    

def ner(
        xml_path: Annotated[Path, typer.Argument(help="Path to the XML file or path",exists=True)],
        collection_data: Annotated[Path, typer.Argument(help="Path to the collection_data.jsonl file",exists=True)],
        spacy_model: Annotated[str, typer.Argument(help="spaCy model name")] = "es_core_news_lg",
):
    """
    Process an ALTO XML files to extract named entities.

    :param xml_file: Path to the XML file or path
    :param force_update: Force update even if data exists
    """

    # Load or download spaCy model
    try:
        nlp = spacy.load(spacy_model)
    except OSError:
        from spacy.cli.download import download
        download(spacy_model)
    
    nlp = spacy.load(spacy_model)

    # Load the collection data
    collection_data = srsly.read_jsonl(collection_data)
    
    # Process the XML file
    if xml_path.is_dir():
        xml_files = list(xml_path.rglob("*.xml"))
    else:
        xml_files = [xml_path]

    for xml_file in track(xml_files, description="Processing XML files..."):
        parser = etree.XMLParser()
        xml_tree = etree.parse(xml_file, parser)
        text = get_page_fulltext(xml_tree)
        # Process the text with spaCy
        doc = nlp(text)
        # Extract named entities
        ents = [{"text": ent.text, "label": ent.label_} for ent in doc.ents]
        print(ents)
        # Create NamedEntityTag for each entity
        # https://altoxml.github.io/documentation/use-cases/tags/ALTO_tags_usecases.html#named_entity_tagging
        # Add the entity tag to the Tags element
        # <Tags>
        # <NamedEntityTag ID="NE15" LABEL="Location" DESCRIPTION="Lexington"/>
        # …
        # </Tags>
        # then refer to the tag id in the String element
        #<String CONTENT="Lexington" WC="1.0" TAGREFS="NE15" HPOS… VPOS…></String>
        



if __name__ == "__main__":
    typer.run(ner)
