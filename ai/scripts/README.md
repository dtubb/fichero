# AI Scripts Documentation

## Available Scripts

### 1. add_feature.py
Add new feature ideas to the inbox

**Usage:**
```bash
python add_feature.py <feature_name> <description>
```

**Example:**
```bash
python add_feature.py "Audio Transcription" "Add audio file transcription capability"
```

### 2. generate_task.py
Generate complete task structure

**Usage:**
```bash
python generate_task.py <task_id> <feature_area> <task_name> <description>
```

**Example:**
```bash
python generate_task.py TODO-022 frontend "Comparison UI" "Add document comparison interface"
```

## How to Use

### For Humans:

1. **Add Feature Idea**:
   ```bash
   cd ai/scripts
   python add_feature.py "Your Feature" "Description"
   ```

2. **Generate Task**:
   ```bash
   python generate_task.py TODO-XXX feature "Task Name" "Description"
   ```

3. **Manual Updates**:
   - Edit `ai/TODO.md` to add new tasks
   - Move files between `inbox/ideas` and `inbox/planned`
   - Update task status in TODO.md

### For AI:

These scripts are available to me as tools. I can:
- Read and execute them
- Generate files using them
- Update TODO.md programmatically
- Move tasks between states

## Script Requirements

- Python 3.x
- Filesystem permissions
- Proper file paths

## Simple Workflow

### Add New Feature Idea:
```bash
# Navigate to scripts
cd ai/scripts

# Add idea
python add_feature.py "Document Comparison" "Compare document versions"

# Edit the generated file
nano ../inbox/ideas/document-comparison.md
```

### Generate Implementation Tasks:
```bash
# Generate backend task
python generate_task.py TODO-022 backend "Comparison API" "Backend comparison endpoint"

# Generate frontend task  
python generate_task.py TODO-023 frontend "Comparison UI" "Frontend comparison interface"

# Update TODO.md
nano ../TODO.md
```

## File Structure

```
ai/
└── scripts/
    ├── add_feature.py      # Add feature ideas
    ├── generate_task.py    # Generate task structure
    └── README.md           # This file
```

## Best Practices

1. **Start with Ideas**: Use `add_feature.py` for new concepts
2. **Break into Tasks**: Use `generate_task.py` when ready to implement
3. **Update TODO.md**: Keep the master list current
4. **Move Files**: Organize ideas → planned → implementation

## Future Enhancements

- Auto-update TODO.md script
- Task completion script
- Feature prioritization tool
- Dependency mapping