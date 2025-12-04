Implement a new feature following TDD and CLAUDE.md best practices: $ARGUMENTS

## Phase 1: Planning

### 1.1 Understand Requirements
- What is the feature?
- Which components are affected? (engine, router, bff, ui)
- What events need to be added/modified?
- What database changes are needed?

### 1.2 Design Approach
- List 2-3 possible approaches with pros/cons
- Choose the approach with minimal changes
- Identify patterns from similar existing code

### 1.3 Create Task List
Break down into specific tasks:
- [ ] Add data models/types
- [ ] Implement core logic
- [ ] Add event handlers
- [ ] Create API endpoints
- [ ] Add UI components
- [ ] Write tests

## Phase 2: Implementation (TDD)

### 2.1 Write Tests First
For each component:
1. Write failing unit test
2. Implement minimal code to pass
3. Refactor if needed

### 2.2 Follow Patterns
- Engine: Use event bus, Pydantic models, async/await
- Router: Use Gin handlers, proper error handling
- BFF: Use NestJS modules, DTOs, dependency injection
- UI: Use React hooks, TypeScript, Tailwind

### 2.3 Event Contracts
If adding new events:
1. Add schema to `contracts/jsonschema/`
2. Run codegen: `python scripts/codegen_contracts.py`
3. Update affected modules

## Phase 3: Verification

### 3.1 Run Tests
```bash
make test
```

### 3.2 Run Quality Checks
```bash
make lint && make typecheck
```

### 3.3 Manual Testing
If applicable, describe manual test steps.

## Phase 4: Documentation

### 4.1 Update CLAUDE.md
If introducing new patterns, document them in the relevant CLAUDE.md.

### 4.2 Code Comments
Add comments only for non-obvious logic (per CLAUDE.md guidelines).

## Reminders
- Follow existing domain vocabulary
- Use branded types for IDs
- Separate pure logic from I/O
- Prefer composition over inheritance
- Keep functions under 50 lines
