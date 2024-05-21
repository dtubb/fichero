import json
from pathlib import Path
import typer
import yaml

def json_to_yaml(json_file: Path, yaml_file: Path):
    with open(json_file, 'r') as file:
        json_data = json.load(file)

    with open(yaml_file, 'w') as file:
        yaml.dump(json_data, file, default_flow_style=False)

    print(f"Converted {json_file} to {yaml_file}")

def main(folder: Path = typer.Argument(..., help="Path to the folder containing JSON files")):
    if not folder.is_dir():
        print(f"{folder} is not a valid directory.")
        raise typer.Exit(1)

    json_files = list(folder.glob('*.json'))

    if not json_files:
        print(f"No JSON files found in {folder}")
        raise typer.Exit(0)

    for json_file in json_files:
        yaml_file = json_file.with_suffix('.yaml')
        json_to_yaml(json_file, yaml_file)

if __name__ == "__main__":
    typer.run(main)