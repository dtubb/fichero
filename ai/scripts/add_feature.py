#!/usr/bin/env python3
# ai/scripts/add_feature.py

import os
import sys
from datetime import datetime

def add_feature_idea(feature_name, description):
    """Add a new feature idea to the inbox"""
    idea_file = f"ai/inbox/ideas/{feature_name.lower().replace(' ', '-')}.md"

    # Create the idea file
    with open(idea_file, 'w') as f:
        f.write(f"""# Feature Idea: {feature_name}

## Created: {datetime.now().strftime('%Y-%m-%d')}

## Description
{description}

## Status
- Idea phase
- Needs review

## Next Steps
- [ ] Technical feasibility assessment
- [ ] Priority determination
- [ ] Break into implementable tasks

## Notes
- Add any additional thoughts here
- Consider dependencies and requirements
""")

    print(f"✅ Feature idea created: {idea_file}")
    print(f"📝 Edit the file to add more details")

def main():
    if len(sys.argv) < 3:
        print("Usage: python add_feature.py <feature_name> <description>")
        print("Example: python add_feature.py \"Audio Transcription\" \"Add audio file support\"")
        return

    feature_name = sys.argv[1]
    description = ' '.join(sys.argv[2:])
    add_feature_idea(feature_name, description)

if __name__ == "__main__":
    main()