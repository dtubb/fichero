import nomic
import srsly
from nomic import atlas
import csv
import typer
from pathlib import Path
from typing_extensions import Annotated
from rich.progress import track

import spacy
# Tool for assessing the quality of OCR'd text
# Identify significant topics in the collection for research

def _atlas(
    collection_path: Annotated[Path, typer.Argument(help="Path to the collections",exists=True)],

):
    collections_data = srsly.read_jsonl(f'{str(collection_path)}/collections_metadata.jsonl')
    counter = 0
    nlp = spacy.load('es_core_news_lg')
    
    atlas_data = []
    for collection in track(collections_data, description=f'Processing...'):
        collection_subpath = collection_path / collection["id"].split('/')[-1]
        #change uri to url 
        for image in collection['images']:
            image['image'] = image.pop('uri')
            text_file = Path(collection_subpath / image['filename']).with_suffix('.txt')
            if text_file.exists():
                image['text'] = text_file.read_text()
                # get ents 
                doc = nlp(image['text'])
                image['ents'] = " ".join([f'{ent.text} {ent.label_}' for ent in doc.ents])
            else:
                image['text'] = ''
                image['ents'] = ''
            image['collection'] = collection['label']
            # remove alto_filename and filename
            image.pop('alto_filename')
            image.pop('filename')
            image.pop('id')
            # set key order in image dict
            image = {
                "text": image.get('text', None),
                "image": image.get('image', None),
                "collection": image.get('collection', None),
                "ents": image.get('ents', None)
            }
            atlas_data.append(image)

    project = atlas.map_text(data=atlas_data,
                            indexed_field='text',
                            name='Testing map for FMB',
                            colorable_fields=['collection','ents'],
                            build_topic_model=True,
                            description='Need to map the text, use IIIF url to load image.',
                            )

if __name__ == "__main__":
    typer.run(_atlas)