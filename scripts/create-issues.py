#!/usr/bin/env python3
"""
Create GitHub issues for Fichero 0.0.3 through 0.1.0 backend tasks.
"""

import subprocess
import sys
from pathlib import Path
import re

def extract_issues(yaml_content):
    """Extract issues from YAML content."""
    issues = []
    
    # Find all list items starting with "  - title:"
    issue_pattern = r'  - title:\s*["\']?(.+?)["\']?\s*\n\s*body:\s*\|\s*\n((?:    .*\n)*)\n\s*labels:\s*\n((?:      - .*\n)*)'
    
    matches = re.finditer(issue_pattern, yaml_content)
    
    for match in matches:
        title = match.group(1).strip()
        body = match.group(2).strip()
        labels_raw = match.group(3)
        
        # Clean up body (remove leading spaces, pipes)
        body_lines = []
        for line in body.split('\n'):
            line = line.strip()
            if line:
                body_lines.append(line)
        body = '\n'.join(body_lines)
        
        # Extract labels
        labels = []
        for line in labels_raw.strip().split('\n'):
            line = line.strip()
            if line.startswith('- '):
                labels.append(line[2:].strip())
        
        issues.append({
            'title': title,
            'body': body,
            'labels': labels
        })
    
    return issues

def create_gh_issue(issue):
    """Create a GitHub issue using gh CLI."""
    title = issue['title']
    body = issue['body']
    labels = issue['labels']
    
    # Build gh issue create command
    cmd = ['gh', 'issue', 'create', '--title', title, '--body', body]
    
    # Add labels
    for label in labels:
        cmd.extend(['--label', label])
    
    print(f"Running: {' '.join(cmd[:10])}...")
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            print(f"  Created issue successfully")
            # Extract URL if present
            if 'github.com' in result.stdout:
                import re
                url_match = re.search(r'https://github\.com/\S+', result.stdout)
                if url_match:
                    print(f"  URL: {url_match.group()}")
            return True
        else:
            print(f"  FAILED: {result.stderr[:200]}")
            return False
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def main():
    # Path is resolved relative to this script — works from any worktree / project location.
    yaml_file = Path(__file__).resolve().parent / "create-issues.yaml"
    yaml_content = yaml_file.read_text()
    
    print("Creating GitHub issues for Fichero 0.0.3 through 0.1.0...")
    print("=" * 70)
    
    issues = extract_issues(yaml_content)
    print(f"Found {len(issues)} issues to create")
    print()
    
    if not issues:
        print("No issues found!")
        sys.exit(1)
    
    # Show.preview
    print(f"First issue preview:")
    print("-" * 70)
    print(f"Title: {issues[0]['title']}")
    print(f"Body preview: {issues[0]['body'][:200]}...")
    print(f"Labels: {issues[0]['labels']}")
    print()
    
    # Confirm
    response = input(f"Create {len(issues)} issues? [y/N]: ")
    if response.lower() != 'y':
        print("Aborted.")
        sys.exit(0)
    
    print()
    
    # Create issues
    created = 0
    failed = 0
    
    for i, issue in enumerate(issues, 1):
        print(f"[{i}/{len(issues)}] Creating: {issue['title'][:60]}...")
        if create_gh_issue(issue):
            created += 1
        else:
            failed += 1
        print()
    
    print("=" * 70)
    print(f"Summary: {created} created, {failed} failed")

if __name__ == '__main__':
    main()
