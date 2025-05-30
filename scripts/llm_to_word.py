import typer
from pathlib import Path
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.text import WD_BREAK
from rich.console import Console
import json
import srsly
import re
import ast

console = Console()
app = typer.Typer()

def set_document_properties(doc):
    """Set up initial document properties"""
    section = doc.sections[0]
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.left_margin = section.right_margin = Inches(1)
    section.top_margin = section.bottom_margin = Inches(1)

def add_title(doc, title):
    """Add the document title at the top of the document."""
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(title)
    run.font.name = 'Helvetica Neue'
    run.font.size = Pt(24)
    run.font.bold = True
    p.space_after = Pt(18)

def add_section(doc, title, content):
    """Add a section with title and content, no page break."""
    # Add section title
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = p.add_run(title)
    run.font.name = 'Helvetica Neue'
    run.font.size = Pt(12)
    run.font.bold = True
    p.space_after = Pt(6)
    
    # Add content
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = p.add_run(content)
    run.font.name = 'Helvetica Neue'
    run.font.size = Pt(10)
    
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(12)
    p.paragraph_format.line_spacing = 1.15

def format_ner_results(ner_data):
    """Format NER results into a clean, readable format"""
    if not ner_data:
        return "No named entities found."
    
    # If input is a string, try to parse as JSON
    if isinstance(ner_data, str):
        try:
            ner_data = json.loads(ner_data)
        except Exception:
            return ner_data  # Return as-is if not JSON
    
    formatted = []
    # Format persons
    if 'persons' in ner_data:
        formatted.append("Persons:")
        for person, pages in ner_data['persons'].items():
            formatted.append(f"  • {person} (pages {', '.join(map(str, pages))})")
        formatted.append("")
    # Format organizations
    if 'organizations' in ner_data:
        formatted.append("Organizations:")
        for org, pages in ner_data['organizations'].items():
            formatted.append(f"  • {org} (pages {', '.join(map(str, pages))})")
        formatted.append("")
    # Format locations
    if 'locations' in ner_data:
        formatted.append("Locations:")
        for loc, pages in ner_data['locations'].items():
            formatted.append(f"  • {loc} (pages {', '.join(map(str, pages))})")
        formatted.append("")
    # Format dates
    if 'dates' in ner_data:
        formatted.append("Dates:")
        for date, pages in ner_data['dates'].items():
            formatted.append(f"  • {date} (pages {', '.join(map(str, pages))})")
        formatted.append("")
    return "\n".join(formatted)

def format_dublin_core(dc_data):
    """Format Dublin Core metadata into a clean, readable format, supporting multiple records in a string."""
    if not dc_data:
        return "No Dublin Core metadata available."

    records = []
    # If the input is a string, extract all JSON objects and Python dicts
    if isinstance(dc_data, str):
        # Remove markdown code block markers and split into possible records
        # Find all ```json ... ``` blocks
        json_blocks = re.findall(r"```json(.*?)```", dc_data, re.DOTALL)
        # Find all standalone Python dicts (not inside code blocks)
        dict_blocks = re.findall(r"\{[^\{\}\n]+?:.*?\}", dc_data, re.DOTALL)
        # If no code blocks, treat the whole string as one block
        if not json_blocks and not dict_blocks:
            json_blocks = [dc_data]
        # Try to parse each block
        for block in json_blocks:
            try:
                record = json.loads(block.strip())
                records.append(record)
            except Exception:
                continue
        for block in dict_blocks:
            try:
                record = ast.literal_eval(block.strip())
                records.append(record)
            except Exception:
                continue
    elif isinstance(dc_data, dict):
        records = [dc_data]
    elif isinstance(dc_data, list):
        records = dc_data
    else:
        return str(dc_data)

    if not records:
        return "No valid Dublin Core records found."

    # Define the order and labels for Dublin Core fields
    field_order = [
        ('dc:title', 'Title'),
        ('dc:creator', 'Creator'),
        ('dc:contributor', 'Contributors'),
        ('dc:date', 'Date'),
        ('dc:type', 'Type'),
        ('dc:format', 'Format'),
        ('dc:identifier', 'Identifier'),
        ('dc:source', 'Source'),
        ('dc:language', 'Language'),
        ('dc:relation', 'Related Entity'),
        ('dc:coverage', 'Coverage'),
        ('dc:rights', 'Rights'),
        ('dc:description', 'Description'),
        ('dc:subject', 'Subjects')
    ]

    formatted = []
    for idx, dc_data in enumerate(records):
        if len(records) > 1:
            formatted.append(f"Record {idx+1}:")
        for dc_key, label in field_order:
            if dc_key in dc_data:
                value = dc_data[dc_key]
                if isinstance(value, list):
                    formatted.append(f"{label}:")
                    for item in value:
                        if isinstance(item, dict):
                            if 'name' in item and 'role' in item:
                                formatted.append(f"  • {item['name']} ({item['role']})")
                            else:
                                formatted.append(f"  • {json.dumps(item)}")
                        else:
                            formatted.append(f"  • {item}")
                elif isinstance(value, dict):
                    formatted.append(f"{label}:")
                    for k, v in value.items():
                        formatted.append(f"  • {k}: {v}")
                else:
                    formatted.append(f"{label}: {value}")
                formatted.append("")
        if len(records) > 1:
            formatted.append("\n---\n")
    return "\n".join(formatted).strip()

def format_json_value(value):
    """Format a JSON value into a readable string"""
    if isinstance(value, dict):
        formatted = []
        for k, v in value.items():
            if isinstance(v, list):
                formatted.append(f"{k}:")
                for item in v:
                    formatted.append(f"  - {item}")
            else:
                formatted.append(f"{k}: {v}")
        return "\n".join(formatted)
    elif isinstance(value, list):
        return "\n".join(f"- {item}" for item in value)
    else:
        return str(value)

def process_single_file(input_file: Path, output_folder: Path):
    """Process a single summary file"""
    console.print(f"[green]Processing file: {input_file}")
    
    # Create output folder if it doesn't exist
    output_folder.mkdir(parents=True, exist_ok=True)
    
    try:
        # Read summary file
        with open(input_file, 'r', encoding='utf-8') as f:
            summary_data = json.load(f)
        
        # Get folder name from the file path
        folder_name = input_file.parent.parent.name
        
        # Create new document
        doc = Document()
        set_document_properties(doc)
        add_title(doc, folder_name)
        
        # Add metadata section
        metadata = {
            "Source": summary_data.get("source", ""),
            "Config": summary_data.get("config", ""),
            "Timestamp": summary_data.get("timestamp", ""),
            "Steps": summary_data.get("steps", [])
        }
        add_section(doc, "Metadata", format_json_value(metadata))
        
        # Process results
        results = summary_data.get("results", {})
        for step_name, step_result in results.items():
            # Try to parse JSON string if it's a string
            if isinstance(step_result, str):
                try:
                    parsed_result = json.loads(step_result)
                    step_result = parsed_result
                except json.JSONDecodeError:
                    pass
            
            # Format the result based on step type
            if step_name == "extract_ner_multipage":
                formatted_result = format_ner_results(step_result)
            elif step_name == "dublin_core_complete":
                formatted_result = format_dublin_core(step_result)
            elif step_name == "summarize_comprehensive":
                formatted_result = step_result  # Already a string
            else:
                formatted_result = format_json_value(step_result)
            
            add_section(doc, step_name.replace("_", " ").title(), formatted_result)
        
        # Save document
        output_path = output_folder / f"{folder_name}-summary.docx"
        doc.save(str(output_path))
        console.print(f"[green]Saved document: {output_path}")
        
    except Exception as e:
        console.print(f"[red]Error processing {input_file}: {str(e)}")
        import traceback
        console.print(f"[red]Traceback: {traceback.format_exc()}")

@app.command()
def process_file(
    input_file: Path = typer.Argument(..., help="Input summary JSON file"),
    output_folder: Path = typer.Argument(..., help="Output folder for Word document")
):
    """Convert a single LLM output JSON file to a formatted Word document"""
    process_single_file(input_file, output_folder)

@app.command()
def process_folder(
    input_folder: Path = typer.Argument(..., help="Input folder containing LLM output JSONL files"),
    output_folder: Path = typer.Argument(..., help="Output folder for Word documents")
):
    """Convert LLM output JSONL files to formatted Word documents"""
    console.print(f"[green]Converting LLM output in {input_folder} to Word documents")
    
    # Create output folder if it doesn't exist
    output_folder.mkdir(parents=True, exist_ok=True)
    
    # Process each folder in the input directory
    for folder_path in input_folder.iterdir():
        if not folder_path.is_dir():
            continue
            
        console.print(f"\nProcessing folder: {folder_path.name}")
        
        # Look for summary JSONL file
        summary_file = folder_path / f"{folder_path.name}_summary.json"
        if not summary_file.exists():
            console.print(f"[yellow]Warning: No summary file found for {folder_path.name}")
            continue
        
        process_single_file(summary_file, output_folder)

if __name__ == "__main__":
    app() 