import typer
import srsly
from pathlib import Path
from typing_extensions import Annotated


def doc_summary(
    docs: Annotated[Path, typer.Argument(help="Path to docs.json", exists=True)],
):
    """
    Summarize the images in the assets folder.
    - Run NER to identify named entities in the text.
    """
    docs = srsly.read_jsonl(docs)
    for doc in docs:
        print(doc)


if __name__ == "__main__":
    typer.run(doc_summary)
