import typer
import srsly
from pathlib import Path
from typing_extensions import Annotated


def img_summary(
    images: Annotated[Path, typer.Argument(help="Path to images.json", exists=True)],
):
    """
    Summarize the images in the assets folder.
    - Run NER to identify named entities in the text.
    """
    images = srsly.read_jsonl(images)
    for image in images:
        try:
            print(f"Image: {image['filename']}")
            print(f"  - URI: {image['uri']}")
            print(f"  - ID: {image['id']}")
            print(f"  - Istmina ID: {image['istmina_id']}")
            print(f"  - Collection: {image['collection']}")
            print(f"  - Doc: {image['doc']}")
            print(f"  - Box: {image['box']}")
            print()
        except:
            pass


if __name__ == "__main__":
    typer.run(img_summary)
