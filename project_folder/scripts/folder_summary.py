import typer
import openpyxl
from pathlib import Path
import json
import yaml
from langchain.llms import OpenAI
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain

app = typer.Typer()

def process_excel(excel_file: Path, config: dict) -> dict:
    """
    Process the Excel file to extract relevant data.

    :param excel_file: Path to the Excel file
    :param config: Configuration dictionary
    :return: Dictionary containing the extracted data
    """
    workbook = openpyxl.load_workbook(excel_file)
    sheet = workbook.active

    data = {}
    for row in sheet.iter_rows(min_row=2, values_only=True):
        file_name = row[0]
        summary = row[3]
        people = row[4]
        organizations = row[5]
        places = row[6]
        keywords = row[7]
        full_text = row[8]

        data[file_name] = {
            'summary': summary,
            'people': people,
            'organizations': organizations,
            'places': places,
            'keywords': keywords,
            'full_text': full_text
        }

    return data

def generate_case_summary(data: dict, config: dict) -> dict:
    """
    Generate a case summary using the LLM based on the provided data and configuration.

    :param data: Dictionary containing the extracted data
    :param config: Configuration dictionary
    :return: Dictionary containing the generated case summary
    """
    case_summary = {}

    for prompt_name, prompt_config in config["prompts"].items():
        prompt_template = prompt_config["template"]
        prompt_provider = prompt_config["provider"]
        prompt_model = prompt_config["model_name"]

        if prompt_provider == "openai":
            llm = OpenAI(model_name=prompt_model)
        else:
            raise ValueError(f"Unsupported provider: {prompt_provider}")

        prompt = PromptTemplate(
            template=prompt_template,
            input_variables=["data"]
        )

        chain = LLMChain(prompt=prompt, llm=llm)
        result = chain.invoke({"data": json.dumps(data)})

        case_summary[prompt_name] = result

    return case_summary

@app.command()
def main(
    folder_path: Path = typer.Argument(..., help="Path to the folder containing the catalogue.xlsx file"),
    config_file: Path = typer.Argument(..., help="Path to the configuration file")
):
    """
    Process the catalogue.xlsx file and generate a case summary using the LLM.
    """
    excel_file = folder_path / "catalogue.xlsx"
    if not excel_file.exists():
        print(f"catalogue.xlsx file not found in {folder_path}")
        raise typer.Exit(1)

    try:
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading configuration file {config_file}: {e}")
        raise typer.Exit(1)

    data = process_excel(excel_file, config)
    case_summary = generate_case_summary(data, config)

    output_file = folder_path / "case_summary.json"
    with open(output_file, "w") as f:
        json.dump(case_summary, f, indent=2)

    print(f"Case summary generated and saved to {output_file}")

if __name__ == "__main__":
    app()