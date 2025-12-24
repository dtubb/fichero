# Git Update Template

## Simple Git Update Format

```
<type>: <short description>

<detailed changes>
```

## Type Prefixes
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `refactor`: Code refactoring
- `style`: Formatting, missing semicolons, etc.
- `test`: Adding or modifying tests
- `chore`: Build process, dependency updates
- `ai`: AI-related changes

## Examples

### Simple update
```
docs: update README summaries

- Add concise 100-character summaries
- Update folder structure documentation
```

### Feature addition
```
feat: add document search

- Implement semantic search endpoint
- Add search UI components
- Update API documentation
```

### Bug fix
```
fix: correct file import error

- Handle missing file extensions
- Add error validation
- Update test cases
```

### AI-specific update
```
ai: improve task workflow

- Update task template with Q&A format
- Add completion checkmarks
- Document decision process
```

## Rules
- First line: 50-72 characters max
- Use present tense ("add" not "added")
- Be specific about what changed
- Group related changes together
- Keep it simple and clear