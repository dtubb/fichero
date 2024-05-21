import typer
import os
from pathlib import Path
from subprocess import call
import re

app = typer.Typer()

def natural_sort_key(s):
    """
    A sorting key to sort strings alphanumerically.
    """
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

@app.command()
def batch_apply_prompt(source_directory: Path, prompt_template_file: Path, variables_file: Path, llm_model: str = "mistral:instruct"):
    """
    Apply the prompt to all files in the given directory, skipping files that already have a processed output.

    :param source_directory: Directory containing text files to process.
    :param prompt_template_file: File containing the prompt template.
    :param variables_file: JSON file containing variables for the prompt.
    :param llm_model: The LLM model to use.
    """
    # Ensure the source directory exists
    if not source_directory.is_dir():
        typer.echo(f"The directory {source_directory} does not exist.")
        raise typer.Exit()

    # Get the root name of the prompt file (without the extension)
    prompt_root_name = prompt_template_file.stem

    # Get all files in the directory and sort them
    files = sorted(source_directory.iterdir(), key=lambda file: natural_sort_key(file.name))

    # Iterate over all files in the directory
    for file in files:
        # Skip if it's not a file
        if not file.is_file():
            continue

        # Construct the output file name
        output_file = source_directory / (file.stem + "_" + prompt_root_name + ".json")

        # Check if the output file already exists
        if output_file.exists():
            typer.echo(f"Output file {output_file} already exists. Skipping file {file.name}.")
            continue

        # Execute the apply_prompt.py script with the file
        call([
            "python", "apply_prompt.py",
            "--source-file", str(file),
            "--prompt-template-file", str(prompt_template_file),
            "--variables-file", str(variables_file),
            "--output-file", str(output_file),
            "--llm-model", llm_model
        ])

if __name__ == "__main__":
    app()