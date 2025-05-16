#!/usr/bin/env python3
import asyncio
import aiohttp
import json
import logging
from pathlib import Path
import typer
from typing import List, Dict
import time
from tqdm import tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = typer.Typer()

async def download_file(session: aiohttp.ClientSession, url: str, output_path: Path, semaphore: asyncio.Semaphore) -> bool:
    """Download a single file with retry logic."""
    max_retries = 3
    retry_delay = 1  # seconds
    
    for attempt in range(max_retries):
        try:
            async with semaphore:
                async with session.get(url) as response:
                    if response.status == 200:
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(output_path, 'wb') as f:
                            f.write(await response.read())
                        return True
                    else:
                        logger.warning(f"Failed to download {url}: HTTP {response.status}")
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed for {url}: {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(retry_delay * (attempt + 1))
    
    logger.error(f"Failed to download {url} after {max_retries} attempts")
    return False

async def process_urls(urls: List[Dict], output_folder: Path, max_workers: int):
    """Process a list of URLs asynchronously."""
    semaphore = asyncio.Semaphore(max_workers)
    async with aiohttp.ClientSession() as session:
        tasks = []
        for url_data in urls:
            url = url_data['url']
            filename = url_data.get('filename', url.split('/')[-1])
            output_path = output_folder / filename
            task = download_file(session, url, output_path, semaphore)
            tasks.append(task)
        
        # Create progress bar
        pbar = tqdm(total=len(tasks), desc="Downloading files")
        
        # Process tasks and update progress
        for completed in asyncio.as_completed(tasks):
            success = await completed
            pbar.update(1)
            if not success:
                pbar.set_postfix_str("Some downloads failed")
        
        pbar.close()

def load_urls(urls_file: Path) -> List[Dict]:
    """Load URLs from a JSONL file."""
    urls = []
    with open(urls_file, 'r') as f:
        for line in f:
            try:
                url_data = json.loads(line.strip())
                if 'url' not in url_data:
                    logger.warning(f"Skipping invalid URL data: {line.strip()}")
                    continue
                urls.append(url_data)
            except json.JSONDecodeError:
                logger.warning(f"Skipping invalid JSON line: {line.strip()}")
    return urls

@app.command()
def main(
    urls_file: Path = typer.Argument(..., help="Path to JSONL file containing URLs"),
    output_folder: Path = typer.Argument(..., help="Folder to save downloaded files"),
    workers: int = typer.Option(10, help="Maximum number of concurrent downloads")
):
    """Download images from URLs asynchronously."""
    try:
        logger.info(f"Loading URLs from {urls_file}")
        urls = load_urls(urls_file)
        logger.info(f"Found {len(urls)} URLs to download")
        
        logger.info(f"Starting downloads to {output_folder}")
        start_time = time.time()
        
        # Run the async download process
        asyncio.run(process_urls(urls, output_folder, workers))
        
        duration = time.time() - start_time
        logger.info(f"Download completed in {duration:.1f} seconds")
        
    except Exception as e:
        logger.error(f"Error during download: {str(e)}")
        raise typer.Exit(1)

if __name__ == "__main__":
    app() 