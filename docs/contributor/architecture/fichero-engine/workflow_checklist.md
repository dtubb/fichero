(AI generated. Not reviewed.)

# Backend Development Workflow Checklist

## New API Endpoint Implementation

### Planning Phase
- [ ] Understand the requirement and desired functionality
- [ ] Review existing similar endpoints for patterns
- [ ] Determine if new database tables/models are needed
- [ ] Identify authentication/authorization requirements

### Implementation Phase
- [ ] Create Pydantic request model in appropriate file
- [ ] Create Pydantic response model
- [ ] Add new route to appropriate router file
- [ ] Implement endpoint logic with proper error handling
- [ ] Add comprehensive docstring documentation
- [ ] Implement proper logging for debugging
- [ ] Add input validation
- [ ] Implement rate limiting if needed

### Database Operations
- [ ] Create/update database schema if needed
- [ ] Implement proper transaction management
- [ ] Add appropriate indexes for performance
- [ ] Implement data validation at database level
- [ ] Consider migration strategy for schema changes

### Testing Phase
- [ ] Write unit tests for validation logic
- [ ] Write unit tests for business logic
- [ ] Write integration tests for full endpoint flow
- [ ] Test error cases and edge conditions
- [ ] Test authentication/authorization
- [ ] Test performance with realistic data volumes
- [ ] Run test suite and verify all tests pass

### Documentation Phase
- [ ] Update API documentation (if separate docs exist)
- [ ] Add examples to docstrings
- [ ] Update any related README files
- [ ] Document any new environment variables

### Review Phase
- [ ] Run linting and code style checks
- [ ] Verify type hints are correct
- [ ] Check for security vulnerabilities
- [ ] Review error handling completeness
- [ ] Verify logging is appropriate
- [ ] Check performance considerations

## New Feature Implementation

### Requirements Analysis
- [ ] Understand user stories and acceptance criteria
- [ ] Identify impacted components
- [ ] Determine API contract changes needed
- [ ] Assess database impact
- [ ] Consider performance implications

### Design Phase
- [ ] Create technical design document (if complex)
- [ ] Define data models and relationships
- [ ] Design API endpoints and contracts
- [ ] Plan database schema changes
- [ ] Consider caching strategy
- [ ] Plan error handling approach

### Implementation Phase
- [ ] Implement database changes first
- [ ] Add new API endpoints
- [ ] Implement business logic
- [ ] Add proper error handling
- [ ] Implement logging
- [ ] Add configuration options
- [ ] Implement feature flags if needed

### Testing Strategy
- [ ] Write unit tests for new components
- [ ] Write integration tests for feature flows
- [ ] Test error conditions and edge cases
- [ ] Test performance under load
- [ ] Test security considerations
- [ ] Test backward compatibility
- [ ] Write end-to-end tests if applicable

### Deployment Considerations
- [ ] Plan database migration strategy
- [ ] Consider data migration needs
- [ ] Plan rollback strategy
- [ ] Update deployment documentation
- [ ] Add monitoring for new functionality
- [ ] Plan feature flag management

## Bug Fix Workflow

### Triage
- [ ] Reproduce the issue
- [ ] Determine severity and priority
- [ ] Identify root cause
- [ ] Assess impact on users

### Fix Implementation
- [ ] Write test that reproduces the bug
- [ ] Implement minimal fix
- [ ] Add proper error handling
- [ ] Update logging if needed
- [ ] Consider adding metrics

### Verification
- [ ] Verify fix resolves the issue
- [ ] Test related functionality for regressions
- [ ] Run full test suite
- [ ] Test in staging environment if available
- [ ] Update documentation if behavior changed

### Post-Fix
- [ ] Monitor for recurrence
- [ ] Consider adding automated monitoring
- [ ] Review similar code for same issue
- [ ] Update runbook if needed