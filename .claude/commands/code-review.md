Perform a comprehensive code review of recent changes in this trading platform:

## Review Checklist

### 1. Code Quality
- [ ] Functions follow CLAUDE.md best practices (readable, low complexity, proper naming)
- [ ] TypeScript: Strict types, no `any`, proper `import type`
- [ ] Python: Pydantic models for data, async/await consistency
- [ ] Go: Proper error handling, no naked returns

### 2. Architecture
- [ ] Changes follow event-driven architecture
- [ ] New modules communicate via event bus, not direct calls
- [ ] No circular dependencies introduced

### 3. Testing
- [ ] Unit tests for new business logic
- [ ] Integration tests for DB/API changes
- [ ] Tests follow CLAUDE.md testing best practices
- [ ] No unexplained literals in tests

### 4. Security
- [ ] No hardcoded secrets or API keys
- [ ] Proper input validation at boundaries
- [ ] SQL injection prevention (parameterized queries)
- [ ] XSS prevention in UI

### 5. Performance
- [ ] No blocking I/O in async code
- [ ] Proper use of connection pooling
- [ ] No N+1 query patterns
- [ ] Chart updates within 150ms target

### 6. Domain Consistency
- [ ] Uses correct vocabulary (candle, pivot, CHOCH, BOS, zone)
- [ ] Event types follow contracts (candles.v1, features.v1, etc.)
- [ ] Decimal handling for prices/quantities

## Instructions

1. Run `git diff HEAD~5` to see recent changes
2. Review each changed file against the checklist
3. Provide specific feedback with file:line references
4. Suggest improvements with code examples
5. Note any blockers that must be fixed before merge
