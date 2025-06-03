#!/usr/bin/env python3
"""
JSON to Excel converter
Converts JSON summary files from LLM processing to formatted Excel documents
"""

import typer
from pathlib import Path
import json
import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
import logging
from rich.console import Console
from typing import Dict, Any, List

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
console = Console()

def format_excel_worksheet(worksheet, df: pd.DataFrame):
    """Apply formatting to the Excel worksheet"""
    # Set font for all cells
    for row in worksheet.iter_rows():
        for cell in row:
            cell.font = Font(name='Helvetica Neue', size=9)
            cell.alignment = Alignment(wrap_text=True, vertical='top')
    
    # Format header row
    header_font = Font(name='Helvetica Neue', size=9, bold=True)
    header_fill = PatternFill(start_color='E0E0E0', end_color='E0E0E0', fill_type='solid')
    
    for cell in worksheet[1]:
        cell.font = header_font
        cell.fill = header_fill
    
    # Adjust column widths
    for idx, col in enumerate(df.columns):
        max_length = max(
            df[col].astype(str).apply(len).max(),
            len(str(col))
        )
        adjusted_width = min(max_length + 2, 100)  # Cap width at 100
        worksheet.column_dimensions[get_column_letter(idx + 1)].width = adjusted_width

def extract_ner_data(data: Dict) -> List[Dict]:
    """Extract NER data from the JSON into a flat list"""
    ner_entries = []
    
    # Process persons
    if 'persons' in data.get('extract_ner_people_orgs_locations', {}):
        for person in data['extract_ner_people_orgs_locations']['persons']:
            ner_entries.append({
                'Type': 'Person',
                'Name': person['name'],
                'Alternative Spellings': ', '.join(person.get('alternative_spellings', [])),
                'Context': person.get('context', '')
            })
    
    # Process organizations
    if 'organizations' in data.get('extract_ner_people_orgs_locations', {}):
        for org in data['extract_ner_people_orgs_locations']['organizations']:
            ner_entries.append({
                'Type': 'Organization',
                'Name': org['name'],
                'Alternative Spellings': ', '.join(org.get('alternative_spellings', [])),
                'Context': org.get('context', '')
            })
    
    # Process locations
    if 'locations' in data.get('extract_ner_people_orgs_locations', {}):
        for loc in data['extract_ner_people_orgs_locations']['locations']:
            ner_entries.append({
                'Type': 'Location',
                'Name': loc['name'],
                'Alternative Spellings': ', '.join(loc.get('alternative_spellings', [])),
                'Context': loc.get('context', '')
            })
    
    return ner_entries

def extract_timeline_data(data: Dict) -> List[Dict]:
    """Extract timeline data from the JSON"""
    timeline_entries = []
    
    if 'timeline' in data.get('timeline_events', {}):
        for event in data['timeline_events']['timeline']:
            timeline_entries.append({
                'Date': event.get('date', ''),
                'Event': event.get('event', '')
            })
    
    return timeline_entries

def extract_key_people_data(data: Dict) -> List[Dict]:
    """Extract key people data from the JSON"""
    key_people = []
    
    if 'key_people' in data.get('key_people_and_tags', {}):
        for person in data['key_people_and_tags']['key_people']:
            key_people.append({
                'Name': person.get('name', ''),
                'Context': person.get('context', '')
            })
    
    return key_people

def convert_json_to_excel(json_file_path: Path, output_path: Path) -> Dict:
    """Convert JSON file to Excel document"""
    try:
        # Read JSON file
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Create Excel writer
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Create Summary sheet
            summary_data = {
                'Field': ['File Name', 'Summary'],
                'Value': [
                    json_file_path.stem,
                    data.get('results', {}).get('summary', {}).get('summary', '')
                ]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            # Create NER sheet
            ner_entries = extract_ner_data(data.get('results', {}))
            if ner_entries:
                ner_df = pd.DataFrame(ner_entries)
                ner_df.to_excel(writer, sheet_name='Named Entities', index=False)
            
            # Create Timeline sheet
            timeline_entries = extract_timeline_data(data.get('results', {}))
            if timeline_entries:
                timeline_df = pd.DataFrame(timeline_entries)
                timeline_df.to_excel(writer, sheet_name='Timeline', index=False)
            
            # Create Key People sheet
            key_people_entries = extract_key_people_data(data.get('results', {}))
            if key_people_entries:
                key_people_df = pd.DataFrame(key_people_entries)
                key_people_df.to_excel(writer, sheet_name='Key People', index=False)
            
            # Apply formatting to each worksheet
            workbook = writer.book
            for sheet_name in workbook.sheetnames:
                worksheet = workbook[sheet_name]
                df = pd.read_excel(output_path, sheet_name=sheet_name)
                format_excel_worksheet(worksheet, df)
        
        return {
            "outputs": [str(output_path)],
            "source": str(json_file_path),
            "success": True
        }
        
    except Exception as e:
        logger.error(f"Error converting {json_file_path}: {e}")
        return {
            "outputs": [],
            "source": str(json_file_path),
            "success": False,
            "error": str(e)
        }

def process_document(file_path: str, output_folder: Path) -> Dict:
    """Process a single JSON document file"""
    file_path = Path(file_path)
    output_path = output_folder / f"{file_path.stem}.xlsx"
    return convert_json_to_excel(file_path, output_path)

def json_to_excel(
    source_folder: Path = typer.Argument(..., help="Source folder containing JSON files"),
    output_folder: Path = typer.Argument(..., help="Output folder for Excel files")
):
    """Convert JSON summary files to Excel documents"""
    
    console.print(f"[blue]Converting JSON summary files to Excel documents")
    console.print(f"[cyan]Source folder: {source_folder}")
    console.print(f"[cyan]Output folder: {output_folder}")
    
    # Find all documents_summary.json files
    json_files = list(source_folder.rglob("documents_summary.json"))
    
    if not json_files:
        console.print("[red]No documents_summary.json files found!")
        return
    
    console.print(f"[green]Found {len(json_files)} summary files to process")
    
    # Process each file
    for json_file in json_files:
        console.print(f"[cyan]Processing: {json_file}")
        result = process_document(str(json_file), output_folder)
        
        if result["success"]:
            console.print(f"[green]Successfully converted: {json_file}")
        else:
            console.print(f"[red]Failed to convert: {json_file}")
            console.print(f"[red]Error: {result.get('error', 'Unknown error')}")

if __name__ == "__main__":
    typer.run(json_to_excel) 