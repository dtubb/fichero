from pathlib import Path
from spacy.cli._util import Arg
import typer
from rich.progress import track
from PIL import Image

import torch
from kraken import blla
from kraken import serialization


def segment(
    collection_path: Path = Arg(..., help="Path to the collections", exists=True),
):
    if torch.cuda.is_available():
        device = 'cuda'
    else:
        device = 'cpu'

    images = list(collection_path.glob("**/*.jpg"))
    for image in track(images, description="Segmenting images..."):
        filename = image.name
        img = Image.open(image)
        # segment the image using kraken
        baseline_seg = blla.segment(img, device=device)
        alto_xml = serialization.serialize_segmentation(baseline_seg, image_name=filename, image_size=img.size, template='alto')
        image.with_suffix('.xml').write_text(alto_xml)

if __name__ == "__main__":
    typer.run(segment)
