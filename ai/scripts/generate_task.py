#!/usr/bin/env python3
# ai/scripts/generate_task.py

import os
import sys

def generate_task(task_id, feature_area, task_name, description):
    """Generate a complete task structure"""
    task_dir = f"ai/tasks/{feature_area}/{task_id}"

    # Create task directory
    os.makedirs(task_dir, exist_ok=True)

    # Create task.md
    with open(f"{task_dir}/task.md", 'w') as f:
        f.write(f"""# {task_id}: {task_name}

## Summary
{description}

## Steps
1. [ ] Implementation step 1
2. [ ] Implementation step 2
3. [ ] Add proper error handling
4. [ ] Write unit tests
5. [ ] Write integration tests

## Files
- File1
- File2

## Testing
- Test case 1
- Test case 2
""")

    # Create context.md
    with open(f"{task_dir}/context.md", 'w') as f:
        f.write(f"""# Context for {task_id}

## Feature Context
- Part of {feature_area} feature area
- Related to [specific feature]

## Technical Requirements
- Use appropriate patterns
- Follow project conventions
- Implement proper error handling

## Specific Requirements
- Requirement 1
- Requirement 2
""")

    # Create workflow.md
    with open(f"{task_dir}/workflow.md", 'w') as f:
        f.write(f"""# Workflow for {task_id}

## Implementation Steps

### 1. Setup
- Review existing implementation
- Check dependencies

### 2. Implementation
- Implement core functionality
- Add error handling
- Connect components

### 3. Testing
- Write unit tests
- Write integration tests
- Test edge cases

### 4. Completion
- Update TODO.md
- Request review
- Move to completed
""")

    print(f"✅ Task generated: {task_dir}")
    print(f"📝 Edit the files to add specific details")

def main():
    if len(sys.argv) < 5:
        print("Usage: python generate_task.py <task_id> <feature_area> <task_name> <description>")
        print("Example: python generate_task.py TODO-022 frontend \"Comparison UI\" \"Add document comparison interface\"")
        return

    task_id = sys.argv[1]
    feature_area = sys.argv[2]
    task_name = sys.argv[3]
    description = ' '.join(sys.argv[4:])
    generate_task(task_id, feature_area, task_name, description)

if __name__ == "__main__":
    main()