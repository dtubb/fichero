import typer
import lxml.etree as etree
from pathlib import Path
import json
from rich.progress import Progress
import yaml
import pprint
from langchain_community.chat_models import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatAnthropic
from langchain.text_splitter import CharacterTextSplitter
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain

app = typer.Typer()

def process_xml(xml_file: Path, config: dict, force_update: bool = False) -> None:
    """
    Process an XML file to extract named entities and update the XML file.

    :param xml_file: Path to the XML file
    :param config: Configuration dictionary
    :param force_update: Force update even if data exists
    """
    
    # Check if the XML file has already been processed
    catalogue_json_file = xml_file.with_suffix(".catalogue.json")
    if catalogue_json_file.exists() and not force_update:
        # Check if the catalogue.json file is empty
        if catalogue_json_file.stat().st_size == 0:
            # If the catalogue.json file is empty, process the XML file
            pass
        else:
            # If the catalogue.json file is not empty, skip the file
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
        # Create an empty catalogue.json file
        try:
            with open(catalogue_json_file, "w", encoding="utf-8") as f:
                json.dump({}, f)
        except Exception as e:
            print(f"Error writing {catalogue_json_file.name}: {e}")
        return

    # Get the full text from the String element
    full_text = string_elem.get("CONTENT", "")

    """
    ======================================
    APPLY LLM PROMPTS FROM CONFIG
    ========================
    """
    catalogue_data = {}

    for prompt_name, prompt_config in config["prompts"].items():
        prompt_template = prompt_config["template"]
        prompt_provider = prompt_config["provider"]
        prompt_model = prompt_config["model_name"]

        try:
            if prompt_provider == "ollama":
                llm = ChatOllama(model=prompt_model, format="json", temperature=0)
                print(f"\nGenerating `{prompt_name}` using LLM ollama with {prompt_model}")
            elif prompt_provider == "openai":
                print(f"\nGenerating `{prompt_name}` using LLM openai with {prompt_model}")
                llm = ChatOpenAI(model_name=prompt_model)
            elif prompt_provider == "claude":
                print(f"\nGenerating `{prompt_name}` using LLM claude with {prompt_model}")
                llm = ChatAnthropic(model=prompt_model)
            else:
                raise ValueError(f"Unsupported provider: {prompt_provider}")

            prompt = PromptTemplate(
                template=prompt_template,
                input_variables=["text"]
            )

            chain = LLMChain(prompt=prompt, llm=llm)
            result = chain.invoke({"text": full_text})["text"]

            try:
                prompt_result = json.loads(result)
                catalogue_data[prompt_name] = prompt_result[prompt_name]
                pprint.pprint(catalogue_data[prompt_name])
            except json.JSONDecodeError as e:
                print(f"Error parsing JSON response for {prompt_name}: {e}")
                print(f"Raw response: {result}")
                catalogue_data[prompt_name] = None  # Set the prompt result to None if parsing fails

        except Exception as e:
            print(f"Error generating {prompt_name}: {e}")
            catalogue_data[prompt_name] = None  # Set the prompt result to None if an error occurs

    # Save the catalogue data to a JSON file
    try:
        with open(catalogue_json_file, "w", encoding="utf-8") as f:
            json.dump(catalogue_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error writing {catalogue_json_file.name}: {e}")
        return
    
    # Update the XML file with the catalogue data
    llm_catalogue_elem = etree.Element("{http://www.loc.gov/standards/alto/ns-v4#}LLMCatalogue", nsmap=ns)
    for prompt_name, prompt_result in catalogue_data.items():
        if prompt_result is not None:
            category_elem = etree.SubElement(llm_catalogue_elem, "{http://www.loc.gov/standards/alto/ns-v4#}" + prompt_name.capitalize())
            if isinstance(prompt_result, list):
                for result in prompt_result:
                    result_elem = etree.SubElement(category_elem, "{http://www.loc.gov/standards/alto/ns-v4#}Result")
                    result_elem.text = result
            else:
                result_elem = etree.SubElement(category_elem, "{http://www.loc.gov/standards/alto/ns-v4#}Result")
                result_elem.text = prompt_result
    
    page_elem.append(llm_catalogue_elem)
    
    # Save the updated XML tree
    tree.write(xml_file, encoding="utf-8", xml_declaration=True, pretty_print=True)

@app.command()
def main(
    folder_path: Path = typer.Argument(..., help="Path to the folder containing XML files"),
    config_file: Path = typer.Argument(..., help="Path to the configuration file"),
    force_update: bool = typer.Option(False, "--force", "-f", help="Force update even if data exists"),
):
    """
    Process XML files in a folder to extract named entities and update the XML files.
    """

    # Load configuration from the provided file
    try:
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading configuration file {config_file}: {e}")
        raise typer.Exit(1)

    xml_files = list(folder_path.rglob("*.xml"))

    total_files = len(xml_files)
    print(f"Processing {total_files} files...")

    with Progress() as progress:
        task = progress.add_task("[green]Processing...", total=total_files)
        skipped_files_count = 0
        processed_files_count = 0

        for xml_file in xml_files:
            catalogue_json_file = xml_file.with_suffix(".catalogue.json")
            if catalogue_json_file.exists() and not force_update:
                skipped_files_count += 1
                continue

            process_xml(xml_file, config, force_update)
            processed_files_count += 1
            progress.update(task, advance=1)

        if skipped_files_count > 0:
            print(f"{skipped_files_count} files were skipped.")

    print(f"Processed {processed_files_count} files.")

if __name__ == "__main__":
    app()