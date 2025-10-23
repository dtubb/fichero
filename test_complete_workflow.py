"""
Complete workflow test - trace all path expansions
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero.tools.build_documents_manifest import build_documents_manifest_batch
from fichero.tools.prepare_images import prepare_images_batch

# Simulate what the workflow executor does
print("=" * 80)
print("SIMULATING WORKFLOW EXECUTION")
print("=" * 80)

# These are the paths the workflow would use
output_path = Path("/Users/dtubb/Documents/fichero/Tiny Test/1931 Antonio Asprilla pide que se haga efectiva una multa a M.C. Marshall y Manuel A. Peña; Istmina")
documents_folder = Path("/Users/dtubb/Documents/fichero/Tiny Test/1931 Antonio Asprilla pide que se haga efectiva una multa a M.C. Marshall y Manuel A. Peña; Istmina")

variables = {
    'documents_folder': str(documents_folder),
    'add_documents_prefix': False
}

print(f"\nWorkflow Variables:")
print(f"  output_path: {output_path}")
print(f"  documents_folder: {variables['documents_folder']}")
print(f"  add_documents_prefix: {variables['add_documents_prefix']}")

# STEP 1: build_documents_manifest
print("\n" + "=" * 80)
print("STEP 1: build_documents_manifest")
print("=" * 80)

# In the YAML: source_folder: "documents"
# Workflow executor expands "documents" to documents_folder variable
source_folder_arg = variables['documents_folder']  # This is what gets passed
output_manifest_arg = output_path / "assets/manifests/documents_manifest.jsonl"

print(f"\nArgs passed to build_documents_manifest_batch:")
print(f"  source_folder={source_folder_arg}")
print(f"  output_manifest={output_manifest_arg}")
print(f"\nChecking if source_folder exists: {Path(source_folder_arg).exists()}")
print(f"Files in source_folder:")
for f in Path(source_folder_arg).iterdir():
    if f.is_file() and f.suffix.lower() in ['.jpg', '.jpeg', '.png']:
        print(f"  - {f.name}")

# Run it
result = build_documents_manifest_batch(
    source_folder=Path(source_folder_arg),
    output_manifest=output_manifest_arg
)
print(f"\n✅ Result: {result}")

# Check the manifest
print(f"\nGenerated manifest:")
with open(output_manifest_arg, 'r') as f:
    lines = f.readlines()
    print(f"  {len(lines)} entries")
    for line in lines[:3]:
        print(f"  - {line.strip()}")

# STEP 2: prepare_images
print("\n" + "=" * 80)
print("STEP 2: prepare_images")
print("=" * 80)

# In the YAML:
#   source_folder: "documents"
#   source_manifest: "assets/manifests/documents_manifest.jsonl"
#   add_documents_prefix: false

source_folder_arg = variables['documents_folder']  # Expanded from "documents"
source_manifest_arg = output_path / "assets/manifests/documents_manifest.jsonl"
output_folder_arg = output_path / "assets/prepared"
add_documents_prefix_arg = False  # From YAML

print(f"\nArgs passed to prepare_images_batch:")
print(f"  source_folder={source_folder_arg}")
print(f"  source_manifest={source_manifest_arg}")
print(f"  output_folder={output_folder_arg}")
print(f"  add_documents_prefix={add_documents_prefix_arg}")

# Run it
result = prepare_images_batch(
    source_folder=Path(source_folder_arg),
    source_manifest=source_manifest_arg,
    output_folder=output_folder_arg,
    add_documents_prefix=add_documents_prefix_arg
)
print(f"\n✅ Result: {result}")

print("\n" + "=" * 80)
print("WORKFLOW COMPLETE")
print("=" * 80)
