#!/usr/bin/env python3
import logging
from pathlib import Path
import typer
import shutil
import platform
import subprocess
import asyncio
import aiohttp
import json
import yaml
from tqdm import tqdm
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import re
from PIL import Image
import os

from scripts.utils.file_manager import FileManager
from scripts.utils.jsonl_manager import JSONLManager
from scripts.utils.workflow_progress import create_progress_tracker
from scripts.utils.logging_utils import rich_log, setup_logging

app = typer.Typer()

def validate_image(file_path: Path) -> bool:
    """Validate that a file is a valid image."""
    try:
        with Image.open(file_path) as img:
            img.verify()  # Verify it's an image
            return True
    except Exception as e:
        rich_log("error", f"Invalid image file {file_path}: {str(e)}")
        return False

def copy_file_mac(source: Path, dest: Path) -> bool:
    """Copy a file on Mac using cp -c for instant copy."""
    try:
        # Create parent directories if they don't exist
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        # Use cp -c for instant copy on Mac
        result = subprocess.run(['cp', '-c', str(source), str(dest)], 
                              capture_output=True, text=True)
        if result.returncode != 0:
            rich_log("error", f"Error copying {source}: {result.stderr}")
            return False
        return True
    except Exception as e:
        rich_log("error", f"Error copying {source}: {str(e)}")
        return False

def copy_file_other(source: Path, dest: Path) -> bool:
    """Copy a file on non-Mac platforms."""
    try:
        # Create parent directories if they don't exist
        dest.parent.mkdir(parents=True, exist_ok=True)
        
        # Use shutil.copy2 to preserve metadata
        shutil.copy2(source, dest)
        return True
    except Exception as e:
        rich_log("error", f"Error copying {source}: {str(e)}")
        return False

async def download_file(session: aiohttp.ClientSession, url: str, dest: Path, semaphore: asyncio.Semaphore) -> bool:
    """Download a file with retry logic and validation."""
    async with semaphore:
        for attempt in range(3):  # Try up to 3 times
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        # Create parent directories if they don't exist
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        
                        # Save the file
                        with open(dest, 'wb') as f:
                            async for chunk in response.content.iter_chunked(8192):
                                f.write(chunk)
                        
                        # Validate the downloaded file
                        if validate_image(dest):
                            return True
                        else:
                            dest.unlink()  # Delete invalid file
                            rich_log("warning", f"Invalid image downloaded from {url}")
                    else:
                        rich_log("warning", f"Failed to download {url}: HTTP {response.status}")
            except Exception as e:
                rich_log("warning", f"Attempt {attempt + 1} failed for {url}: {str(e)}")
                if attempt < 2:  # Don't sleep on the last attempt
                    await asyncio.sleep(1)
        return False

async def extract_image_urls(session: aiohttp.ClientSession, url: str, selector: str = None) -> list[str]:
    """Extract image URLs from an HTML page."""
    try:
        async with session.get(url) as response:
            if response.status == 200:
                html = await response.text()
                soup = BeautifulSoup(html, 'html.parser')
                
                if selector:
                    # Use provided CSS selector
                    elements = soup.select(selector)
                else:
                    # Default to all img tags
                    elements = soup.find_all('img')
                
                # Extract URLs
                urls = []
                for element in elements:
                    if element.get('src'):
                        # Handle relative URLs
                        img_url = element['src']
                        if not img_url.startswith(('http://', 'https://')):
                            img_url = urlparse(url)._replace(path=img_url).geturl()
                        urls.append(img_url)
                return urls
            else:
                rich_log("warning", f"Failed to fetch {url}: HTTP {response.status}")
                return []
    except Exception as e:
        rich_log("error", f"Error extracting images from {url}: {str(e)}")
        return []

async def process_html_source(session: aiohttp.ClientSession, source: dict, output_folder: Path) -> list[str]:
    """Process an HTML source configuration."""
    urls = []
    if 'url' in source:
        # Extract image URLs from the page
        selector = source.get('selector')
        page_urls = await extract_image_urls(session, source['url'], selector)
        urls.extend(page_urls)
        
        # Handle pagination if specified
        if 'pagination' in source:
            pagination = source['pagination']
            pattern = pagination.get('pattern')
            start = pagination.get('start', 1)
            end = pagination.get('end', 1)
            
            for page in range(start, end + 1):
                page_url = pattern.format(page=page)
                page_urls = await extract_image_urls(session, page_url, selector)
                urls.extend(page_urls)
    
    return urls

async def download_urls(urls_file: Path, output_folder: Path, max_workers: int = 10):
    """Download files from URLs asynchronously."""
    # Create output folder if it doesn't exist
    output_folder.mkdir(parents=True, exist_ok=True)
    
    # Load URLs based on file type
    urls = []
    if urls_file.suffix == '.jsonl':
        # Load from JSONL
        jsonl_manager = JSONLManager(str(urls_file))
        entries = jsonl_manager.read_all()
        urls = [entry['url'] for entry in entries if 'url' in entry]
    elif urls_file.suffix in ['.yaml', '.yml']:
        # Load from YAML
        with open(urls_file) as f:
            config = yaml.safe_load(f)
            
            # Process HTML sources
            async with aiohttp.ClientSession() as session:
                if 'html_sources' in config:
                    for source in config['html_sources']:
                        source_urls = await process_html_source(session, source, output_folder)
                        urls.extend(source_urls)
                
                # Add direct URLs if any
                if 'direct_urls' in config:
                    urls.extend(config['direct_urls'])
    
    rich_log("info", f"Found {len(urls)} URLs to download")
    
    # Set up async download
    semaphore = asyncio.Semaphore(max_workers)
    async with aiohttp.ClientSession() as session:
        tasks = []
        for url in urls:
            # Create filename from URL
            filename = Path(urlparse(url).path).name
            if not filename:
                filename = f"file_{len(tasks)}"
            dest = output_folder / filename
            
            tasks.append(download_file(session, url, dest, semaphore))
        
        # Download with progress bar
        success_count = 0
        for coro in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Downloading files"):
            if await coro:
                success_count += 1
        
        rich_log("info", f"Successfully downloaded {success_count} of {len(urls)} files")

def prepare_local_folder(source_folder: Path, output_folder: Path):
    """Copy all files from source to output folder."""
    # Create output folder if it doesn't exist
    output_folder.mkdir(parents=True, exist_ok=True)
    
    # Get all files (including hidden ones)
    input_files = list(source_folder.glob('**/*'))
    input_files = [f for f in input_files if f.is_file()]  # Only files, not directories
    
    rich_log("info", f"Found {len(input_files)} files to prepare")
    
    # Choose copy function based on platform
    copy_func = copy_file_mac if platform.system() == 'Darwin' else copy_file_other
    
    # Process each file
    success_count = 0
    for input_path in tqdm(input_files, desc="Preparing files"):
        # Create output path maintaining folder structure
        rel_path = input_path.relative_to(source_folder)
        output_path = output_folder / rel_path
        
        if copy_func(input_path, output_path):
            # Validate the copied file
            if validate_image(output_path):
                success_count += 1
            else:
                # Delete invalid file
                output_path.unlink()
                rich_log("error", f"Invalid image file: {input_path}")
    
    rich_log("info", f"Successfully prepared {success_count} of {len(input_files)} files")

@app.command()
def main(
    source: Path = typer.Argument(..., help="Source folder containing files to prepare, JSONL file with URLs, or YAML file with HTML sources"),
    output_folder: Path = typer.Argument(..., help="Folder to copy/download files to"),
    max_workers: int = typer.Option(10, help="Maximum number of concurrent downloads"),
    debug: bool = typer.Option(False, help="Enable debug logging")
):
    """Prepare images by copying from local folder or downloading from URLs/HTML sources."""
    # Set up logging
    setup_logging(level=logging.DEBUG if debug or os.environ.get('FICHERO_DEBUG') == '1' else logging.INFO)
    
    try:
        rich_log("info", f"Preparing files from {source}")
        
        if source.suffix in ['.jsonl', '.yaml', '.yml']:
            # Download from URLs or HTML sources
            asyncio.run(download_urls(source, output_folder, max_workers))
        else:
            # Copy from local folder
            prepare_local_folder(source, output_folder)
            
        rich_log("info", "Preparation completed")
        
    except Exception as e:
        rich_log("error", f"Error during preparation: {str(e)}")
        raise typer.Exit(1)

if __name__ == "__main__":
    app() 