Analyze and fix GitHub issue: $ARGUMENTS

## Process

### Step 1: Gather Context
```bash
gh issue view $ARGUMENTS
```

### Step 2: Understand the Problem
- Read the issue description and comments
- Identify affected components (engine, router, bff, ui)
- Note any error messages or stack traces

### Step 3: Locate Relevant Code
- Search codebase for relevant files using `rg`
- Read the appropriate CLAUDE.md for that component
- Understand existing patterns before modifying

### Step 4: Implement Fix
- Follow TDD: write failing test first
- Make minimal changes to fix the issue
- Follow existing code patterns

### Step 5: Verify
- Run relevant tests: `make test-engine` or `make test-bff` etc.
- Run linting: `make lint`
- Run type checking: `make typecheck`

### Step 6: Commit
- Stage changes: `git add -A`
- Create commit with Conventional Commits format:
  ```
  fix(component): description of fix

  Fixes #ISSUE_NUMBER
  ```

### Step 7: Create PR
```bash
gh pr create --title "fix(component): description" --body "Fixes #$ARGUMENTS"
```

## Reminders
- MUST follow CLAUDE.md best practices
- MUST NOT refer to Claude/Anthropic in commits
- MUST run tests before PR
- SHOULD prefer minimal changes
- SHOULD update tests if behavior changes
