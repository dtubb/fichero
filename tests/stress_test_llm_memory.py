#!/usr/bin/env python3
"""
Stress test for LLM memory usage.

This script makes multiple concurrent and sequential LLM calls
to test memory stability and resource management.
"""

import asyncio
import time
import sys
import os
from typing import List

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fichero.llm import LLMConfig, chat, embed, chat_with_tools


async def make_single_call(call_num: int, config: LLMConfig) -> str:
    """Make a single LLM call with progress tracking."""
    prompt = f"Call #{call_num}: Tell me a short story about a programmer debugging code at 3am. Include the word 'fichero' somewhere in the story."
    
    start_time = time.time()
    try:
        response = await chat(prompt, config)
        elapsed = time.time() - start_time
        print(f"✓ Call {call_num} completed in {elapsed:.2f}s (length: {len(response)} chars)")
        return response
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"✗ Call {call_num} failed after {elapsed:.2f}s: {e}")
        raise


async def make_sequential_calls(count: int, config: LLMConfig) -> List[str]:
    """Make sequential LLM calls."""
    print(f"\n=== Starting {count} sequential calls ===")
    results = []
    
    for i in range(1, count + 1):
        results.append(await make_single_call(i, config))
        
        # Print memory stats periodically
        if i % 10 == 0 or i == count:
            print(f"\n--- After {i} calls ---")
            print(f"Total responses: {len(results)}")
            print(f"Total characters: {sum(len(r) for r in results)}")
    
    return results


async def make_concurrent_calls(count: int, config: LLMConfig, batch_size: int = 5) -> List[str]:
    """Make concurrent LLM calls in batches."""
    print(f"\n=== Starting {count} concurrent calls (batch size: {batch_size}) ===")
    results = []
    
    # Split into batches
    for batch_num in range(0, count, batch_size):
        batch_start = batch_num + 1
        batch_end = min(batch_num + batch_size, count)
        
        print(f"\n--- Batch {batch_num // batch_size + 1}: Calls {batch_start}-{batch_end} ---")
        
        # Create tasks for this batch
        tasks = []
        for i in range(batch_start, batch_end + 1):
            tasks.append(make_single_call(i, config))
        
        # Run batch concurrently
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check for failures
        for i, result in enumerate(batch_results):
            if isinstance(result, Exception):
                print(f"ERROR in batch call {batch_start + i}: {result}")
            else:
                results.append(result)
    
    return results


async def test_embeddings(count: int, config: LLMConfig) -> List[List[float]]:
    """Test embedding generation."""
    print(f"\n=== Testing embeddings ({count} texts) ===")
    
    # Create test texts
    texts = [f"This is test text number {i} for embedding generation." for i in range(count)]
    
    start_time = time.time()
    try:
        embeddings = await aembed(texts, model="text-embedding-3-small")
        elapsed = time.time() - start_time
        print(f"✓ Generated {len(embeddings)} embeddings in {elapsed:.2f}s")
        print(f"  First embedding dimension: {len(embeddings[0]) if embeddings else 0}")
        return embeddings
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"✗ Embedding generation failed after {elapsed:.2f}s: {e}")
        raise


async def test_tool_calls(count: int, config: LLMConfig) -> List[dict]:
    """Test tool/function calling."""
    print(f"\n=== Testing tool calls ({count} calls) ===")
    
    # Define a simple tool
    tools = [{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for a location",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string"},
                    "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]}
                },
                "required": ["location"]
            }
        }
    }]
    
    results = []
    for i in range(1, count + 1):
        prompt = f"Call #{i}: What's the weather in San Francisco today? Use the get_weather tool."
        
        start_time = time.time()
        try:
            result = await chat_with_tools(prompt, tools, config)
            elapsed = time.time() - start_time
            print(f"✓ Tool call {i} completed in {elapsed:.2f}s")
            results.append(result)
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"✗ Tool call {i} failed after {elapsed:.2f}s: {e}")
            raise
    
    return results


async def run_memory_stress_test():
    """Run comprehensive memory stress test."""
    
    # Configuration - use a fast, affordable model
    config = LLMConfig(
        provider="openai",
        model="gpt-4o-mini",
        temperature=0.7,
        max_tokens=1024,
        timeout=120
    )
    
    print("=" * 70)
    print("LLM Memory Stress Test")
    print("=" * 70)
    print(f"Model: {config.get_model_name()}")
    print(f"Temperature: {config.temperature}")
    print(f"Max tokens: {config.max_tokens}")
    print("=" * 70)
    
    try:
        # Test 1: Sequential calls
        await make_sequential_calls(20, config)
        
        # Test 2: Concurrent calls
        await make_concurrent_calls(20, config, batch_size=5)
        
        # Test 3: Embeddings
        await test_embeddings(10, config)
        
        # Test 4: Tool calls
        await test_tool_calls(5, config)
        
        # Final summary
        print("\n" + "=" * 70)
        print("✓ All stress tests completed successfully!")
        print("=" * 70)
        
    except Exception as e:
        print(f"\n✗ Stress test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Check if API key is available
    from fichero.llm import get_api_key
    api_key = get_api_key("openai")
    
    if not api_key:
        print("ERROR: No OpenAI API key found!")
        print("Please set OPENAI_API_KEY environment variable or add it to your keychain.")
        sys.exit(1)
    
    print(f"Using OpenAI API key: {'*' * 8}...{'*' * 8}")
    print()
    
    # Run the test
    asyncio.run(run_memory_stress_test())
