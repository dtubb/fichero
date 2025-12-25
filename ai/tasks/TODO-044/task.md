# TODO-044: Implement Core Workflow Engine with LangGraph

## What to do
Implement the core workflow executor with LangGraph integration for document processing

## Steps
- [ ] Step 1: Create WorkflowExecutor class in src/fichero/workflows/executor.py
- [ ] Step 2: Implement LangGraph StateGraph integration for workflow execution BUT also use LangGraph Pregel Execution Engine. https://the-pocket.github.io/PocketFlow-Tutorial-Codebase-Knowledge/LangGraph/05_pregel_execution_engine.html
- [ ] Step 3: Add document state management for tracking progress through workflow
- [ ] Step 4: Implement progress event system for real-time UI updates
- [ ] Step 5: Add error handling and retry logic for robust execution
- [ ] Step 6: Implement concurrent execution with resource management
- [ ] Step 7: Create basic unit tests for workflow execution
- [ ] Step 8: Test with simple workflow definitions

## Files
- File to create: src/fichero/workflows/executor.py (new core executor)
- File to create: src/fichero/workflows/state.py (document state management)
- File to modify: src/fichero/workflows/types.py (extend workflow types)
- File to create: tests/unit/test_workflow_executor.py (unit tests)

## Questions for Human
- [ ] Question 1: Should we use async/await pattern for workflow execution?
    Answer: Yes, based on LangGraph async capabilities and best practices
- [ ] Question 2: What's the expected concurrency model for document processing?
    Answer: Process documents in batches with configurable batch size
- [ ] Question 3: Should we implement resource pooling for API calls?
    Answer: Yes, to handle rate limits and optimize performance

## Answers and Implementation
- Will use LangGraph StateGraph as core execution engine
- Will implement async execution with proper error handling
- Will add resource pooling for concurrent API calls
- Will create comprehensive unit tests for all components
- Will follow the architecture outlined in TODO-042 workflow plan

## Need help?
- Review TODO-042 workflow_plan.md for detailed architecture
- Check LangGraph documentation for StateGraph implementation
- Keep implementation focused and testable