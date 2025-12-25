# TODO-045: Implement Tool Registry System

## What to do
Create the tool registry system for workflow tools with port definitions and discovery API

## Steps
- [x] Step 1: Create ToolRegistry class in src/fichero/workflows/registry.py
- [x] Step 2: Implement tool registration with input/output port definitions
- [x] Step 3: Register existing tools with proper port configurations
- [x] Step 4: Create tool discovery API endpoints in src/fichero/api/routes/workflows.py
- [x] Step 5: Implement tool validation and type checking
- [x] Step 6: Add tool documentation and metadata support
- [x] Step 7: Create unit tests for tool registry functionality
- [x] Step 8: Test tool discovery through API endpoints

## Files
- File to create: src/fichero/workflows/registry.py (tool registry system)
- File to modify: src/fichero/api/routes/workflows.py (add tool discovery endpoints)
- File to create: src/fichero/workflows/tools/ (directory for tool implementations)
- File to create: tests/unit/test_tool_registry.py (unit tests)

## Questions for Human
- [ ] Question 1: What's the expected format for tool port definitions?
    Answer: Use JSON schema format for port type definitions
- [ ] Question 2: Should tools be dynamically discoverable or statically registered?
    Answer: Start with static registration, plan for dynamic discovery later
- [ ] Question 3: What validation rules should be enforced for tool connections?
    Answer: Type compatibility and required port validation

## Answers and Implementation
- Will create comprehensive tool registry with port management
- Will implement API endpoints for tool discovery
- Will add validation for tool connections
- Will follow REST API conventions for endpoints
- Will integrate with workflow executor for tool execution

## Need help?
- Review TODO-042 workflow_plan.md for tool registry architecture
- Check existing tools in codebase for registration patterns
- Keep tool definitions flexible for future expansion